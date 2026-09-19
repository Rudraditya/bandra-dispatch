"""The simulation loop: a background task that ticks once per real second. Vehicles
move continuously along their route at real driving speed (m/s from OSM speed data,
slowed by live congestion) instead of jumping node-to-node. After a delivery, a van
drives back to its home depot before it's eligible for its next assignment."""
import asyncio
import logging
from bisect import bisect_right
from typing import Awaitable, Callable, Optional

import networkx as nx

from app import traffic
from app.dispatch import dispatch_orders
from app.graph_setup import node_lat_lon
from app.routing import edge_speed_kph, path_cumulative_distance
from app.state import FUEL_CHARGE_PER_KM, SLA_THRESHOLD_SEC, SimulationState, Vehicle

TICK_SECONDS = 1.0  # 1 backend tick == 1 real second of simulated driving time
MIN_EFFECTIVE_SPEED_MPS = 1.4  # ~5 km/h floor so gridlock never fully stalls a van

BroadcastCallback = Callable[[SimulationState], Awaitable[None]]


class SimulationEngine:
    def __init__(self, state: SimulationState, broadcast: Optional[BroadcastCallback] = None):
        self.state = state
        self.broadcast = broadcast
        self._task: Optional[asyncio.Task] = None

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run(self):
        while True:
            try:
                self.tick()
            except Exception:
                # This loop is fire-and-forget (nothing ever awaits it), so an
                # unhandled exception here would otherwise kill the simulation
                # silently while the API kept responding as if nothing were wrong.
                logging.exception("Simulation tick failed; continuing from next tick")
            if self.broadcast is not None:
                await self.broadcast(self.state)
            await asyncio.sleep(TICK_SECONDS)

    def tick(self):
        self.state.tick_count += 1
        traffic.update_traffic(self.state.graph, self.state.tick_count)

        # Stress-test orders trickle in one at a time rather than landing all at once.
        if self.state.bulk_queue_remaining > 0:
            self.state.new_random_order()
            self.state.bulk_queue_remaining -= 1

        self.state.drain_waitlists()
        dispatch_orders(self.state)
        self._advance_vehicles()

    def _advance_vehicles(self):
        for vehicle in self.state.vehicles.values():
            if vehicle.status not in ("en_route", "returning"):
                continue

            if vehicle.route_total_m <= 0:
                self._arrive(vehicle)
                continue

            path = vehicle.route_path
            cum = vehicle.route_cum_dist
            seg = max(0, min(bisect_right(cum, vehicle.route_progress_m) - 1, len(path) - 2))
            u, v = path[seg], path[seg + 1]

            speed_kph = edge_speed_kph(self.state.graph, u, v)
            congestion = traffic.edge_congestion(self.state.graph, u, v)
            effective_speed_mps = max(MIN_EFFECTIVE_SPEED_MPS, (speed_kph * 1000 / 3600) / congestion)

            vehicle.route_progress_m = min(
                vehicle.route_total_m, vehicle.route_progress_m + effective_speed_mps * TICK_SECONDS
            )

            if vehicle.route_progress_m >= vehicle.route_total_m:
                vehicle.current_node = path[-1]
                vehicle.lat, vehicle.lon = node_lat_lon(self.state.graph, path[-1])
                self._arrive(vehicle)
            else:
                seg = max(0, min(bisect_right(cum, vehicle.route_progress_m) - 1, len(path) - 2))
                u, v = path[seg], path[seg + 1]
                seg_len = cum[seg + 1] - cum[seg]
                frac = (vehicle.route_progress_m - cum[seg]) / seg_len if seg_len > 0 else 0.0
                lat_u, lon_u = node_lat_lon(self.state.graph, u)
                lat_v, lon_v = node_lat_lon(self.state.graph, v)
                vehicle.current_node = u
                vehicle.lat = lat_u + (lat_v - lat_u) * frac
                vehicle.lon = lon_u + (lon_v - lon_u) * frac

    def _arrive(self, vehicle: Vehicle):
        vehicle.lifetime_distance_m += vehicle.route_total_m
        if vehicle.status == "en_route":
            self._complete_delivery(vehicle)
            self._start_return_trip(vehicle)
        else:  # "returning"
            vehicle.status = "idle"
            vehicle.route_path = []
            vehicle.route_cum_dist = []
            vehicle.route_progress_m = 0.0
            vehicle.route_total_m = 0.0

    def _start_return_trip(self, vehicle: Vehicle):
        if vehicle.current_node == vehicle.depot_node:
            vehicle.status = "idle"
            vehicle.route_path = []
            vehicle.route_cum_dist = []
            vehicle.route_progress_m = 0.0
            vehicle.route_total_m = 0.0
            return

        try:
            path = nx.shortest_path(
                self.state.graph, vehicle.current_node, vehicle.depot_node, weight="current_weight"
            )
            route_graph = self.state.graph
        except nx.NetworkXNoPath:
            # One-way streets can make the directed reverse trip impossible even
            # though the outbound trip found this node reachable from the depot.
            # Falling back to an undirected view guarantees a way home.
            path = nx.shortest_path(
                self.state.undirected_graph,
                vehicle.current_node,
                vehicle.depot_node,
                weight="current_weight",
            )
            route_graph = self.state.undirected_graph

        vehicle.route_path = path
        vehicle.route_cum_dist = path_cumulative_distance(route_graph, path)
        vehicle.route_total_m = vehicle.route_cum_dist[-1]
        vehicle.route_progress_m = 0.0
        vehicle.status = "returning"

    def _complete_delivery(self, vehicle: Vehicle):
        order = self.state.orders.get(vehicle.target_order_id)
        if order is not None:
            order.status = "completed"
            order.completed_tick = self.state.tick_count
            duration_s = order.completed_tick - order.created_tick
            distance_m = vehicle.route_total_m
            fuel_cost = (distance_m / 1000.0) * FUEL_CHARGE_PER_KM

            self.state.response_times_sec.append(duration_s)
            self.state.completed_deliveries += 1
            self.state.completion_ticks.append(order.completed_tick)
            if duration_s <= SLA_THRESHOLD_SEC:
                self.state.sla_within_threshold += 1

            record = {
                "order_id": order.id,
                "vehicle_id": vehicle.id,
                "origin_depot": self.state.depots[vehicle.depot_index].name,
                "depot_index": vehicle.depot_index,
                "duration_s": duration_s,
                "distance_m": round(distance_m, 1),
                "fuel_cost": round(fuel_cost, 2),
                "created_tick": order.created_tick,
                "completed_tick": order.completed_tick,
            }
            self.state.recent_deliveries.appendleft(record)
            self.state.delivery_log.append(record)

        vehicle.target_order_id = None
