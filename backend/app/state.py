"""In-memory state for the dispatch simulation: vehicles, orders, depots, and cost accounting."""
import itertools
import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx

from app import traffic
from app.graph_setup import NUM_DEPOTS, load_graph, nearest_node, node_lat_lon, pick_depot_nodes

TOTAL_VEHICLES = 100  # spread as evenly as possible across NUM_DEPOTS (may not divide evenly)
RECENT_DELIVERIES_MAXLEN = 15
DELIVERY_LOG_MAXLEN = 5000
SLA_THRESHOLD_SEC = 1080  # 18 minutes
COMPLETION_WINDOW = 30  # how many recent completions the ETA's throughput estimate spans
STALE_RATE_TICKS = 60  # no completion in this long -> throughput estimate is unreliable
BALANCE_SLACK = 1.15  # how far above a perfectly even split each depot's partition may go
DEPOT_REFINEMENT_ROUNDS = 4  # Lloyd's-iteration rounds re-centering depots on their partition

# --- Logistics constraint: depot batch capacity + restock ---
DEPOT_BATCH_CAPACITY = 60  # a depot can actively handle at most this many orders at once
RESTOCK_TICKS = 600  # 10 minutes — how long a depot waitlists new orders once over capacity

# --- Cost model (see point 6 of the spec) ---
# Fixed costs are one-time, "per simulation" charges. Warehouse ops & utility are
# per-depot (one warehouse); driver salary & maintenance are per-van (one driver/
# service contract per vehicle) — the natural real-world allocation for each line item.
WAREHOUSE_OPERATION_COST = 1000.0  # rupees, per depot, per simulation
UTILITY_COST = 100.0  # rupees, per depot, per simulation
VAN_DRIVER_SALARY = 500.0  # rupees, per van, per simulation
FLEET_MAINTENANCE_COST = 60.0  # rupees, per van, per simulation
FUEL_CHARGE_PER_KM = 100.0  # rupees, per km actually driven
WAREHOUSE_REFILL_COST = 500.0  # rupees, charged every time a depot restocks


def vans_per_depot(num_depots: int, total_vans: int) -> list[int]:
    """Split `total_vans` across `num_depots` as evenly as possible. When it
    doesn't divide evenly, the first few depots absorb one extra van each rather
    than leaving a remainder unassigned."""
    base, remainder = divmod(total_vans, num_depots)
    return [base + 1 if i < remainder else base for i in range(num_depots)]


@dataclass
class Depot:
    index: int
    node: int
    lat: float
    lon: float
    name: str
    van_count: int = 0
    restock_until_tick: Optional[int] = None
    waitlist: list = field(default_factory=list)  # order ids, FIFO
    orders_handled_total: int = 0
    waitlist_events: int = 0

    def is_restocking(self, tick: int) -> bool:
        return self.restock_until_tick is not None and tick < self.restock_until_tick

    def fixed_cost(self) -> float:
        return (
            WAREHOUSE_OPERATION_COST
            + UTILITY_COST
            + self.van_count * (VAN_DRIVER_SALARY + FLEET_MAINTENANCE_COST)
        )

    def refill_cost(self) -> float:
        return self.waitlist_events * WAREHOUSE_REFILL_COST


@dataclass
class Vehicle:
    id: int
    depot_node: int
    depot_index: int
    current_node: int
    lat: float
    lon: float
    status: str = "idle"  # idle | en_route | returning
    target_order_id: Optional[str] = None
    route_path: list = field(default_factory=list)  # full node path for the current trip
    route_cum_dist: list = field(default_factory=list)  # meters, cumulative, aligned to route_path
    route_progress_m: float = 0.0
    route_total_m: float = 0.0
    lifetime_distance_m: float = 0.0  # accumulated over every completed leg (delivery + return)

    def to_dict(self):
        return {
            "id": self.id,
            "lat": self.lat,
            "lon": self.lon,
            "status": self.status,
            "target_order_id": self.target_order_id,
            "depot_index": self.depot_index,
        }


@dataclass
class Order:
    id: str
    node: int
    lat: float
    lon: float
    home_depot_index: int = 0
    status: str = "pending"  # pending | assigned | completed | waitlisted
    created_tick: int = 0  # tick == elapsed real second since sim start
    completed_tick: Optional[int] = None
    assigned_vehicle_id: Optional[int] = None

    def to_dict(self):
        return {
            "id": self.id,
            "lat": self.lat,
            "lon": self.lon,
            "status": self.status,
            "assigned_vehicle_id": self.assigned_vehicle_id,
            "created_tick": self.created_tick,
            "home_depot_index": self.home_depot_index,
        }


class SimulationState:
    def __init__(self):
        self.graph = load_graph()
        # Read-only fallback for the rare case where one-way streets leave no directed
        # path back to a depot — see SimulationEngine._start_return_trip.
        self.undirected_graph = self.graph.to_undirected(as_view=True)
        self.depot_nodes = pick_depot_nodes(self.graph)
        self.vehicles: dict[int, Vehicle] = {}
        self.orders: dict[str, Order] = {}
        self.depots: list[Depot] = []
        self._order_seq = itertools.count(1)
        self.completed_deliveries = 0
        self.sla_within_threshold = 0
        self.response_times_sec: list[float] = []
        self.recent_deliveries: deque = deque(maxlen=RECENT_DELIVERIES_MAXLEN)
        self.delivery_log: deque = deque(maxlen=DELIVERY_LOG_MAXLEN)
        self.completion_ticks: deque = deque(maxlen=COMPLETION_WINDOW)
        self.bulk_queue_remaining = 0
        self.tick_count = 0
        traffic.init_traffic(self.graph)
        self._init_depots()
        self._init_vehicles()

    def _init_depots(self):
        self.depots = []
        nodes = list(self.graph.nodes)
        depot_nodes = list(self.depot_nodes)
        dist_maps = []
        assignment = {}

        # Lloyd's-algorithm-style refinement: farthest-point seeding alone can leave
        # one depot in a network-sparse corner (technically "far from the others,"
        # but with hardly any nodes actually near it — a handful out of a thousand+).
        # Each round re-partitions by the balanced assignment (E-step), then re-centers
        # every depot onto the node closest to its own partition's centroid (M-step).
        # A depot stranded with a tiny partition drifts toward where its nodes
        # actually are instead of staying pinned to a bad seed point.
        for _ in range(DEPOT_REFINEMENT_ROUNDS):
            dist_maps = [
                nx.single_source_dijkstra_path_length(self.graph, node, weight="travel_time")
                for node in depot_nodes
            ]
            assignment = self._balanced_assignment(nodes, dist_maps)

            new_depot_nodes = []
            for i, node in enumerate(depot_nodes):
                members = [n for n, d in assignment.items() if d == i]
                if not members:
                    new_depot_nodes.append(node)
                    continue
                cx = sum(self.graph.nodes[n]["x"] for n in members) / len(members)
                cy = sum(self.graph.nodes[n]["y"] for n in members) / len(members)
                centroid_node = min(
                    members,
                    key=lambda n: (self.graph.nodes[n]["x"] - cx) ** 2 + (self.graph.nodes[n]["y"] - cy) ** 2,
                )
                new_depot_nodes.append(centroid_node)
            depot_nodes = new_depot_nodes

        self.depot_nodes = depot_nodes
        self._depot_free_flow_dist = dist_maps
        self._node_depot_assignment = assignment

        van_counts = vans_per_depot(len(depot_nodes), TOTAL_VEHICLES)
        for i, node in enumerate(depot_nodes):
            lat, lon = node_lat_lon(self.graph, node)
            self.depots.append(
                Depot(
                    index=i,
                    node=node,
                    lat=lat,
                    lon=lon,
                    name=f"Depot {chr(ord('A') + i)}",
                    van_count=van_counts[i],
                )
            )

    def _balanced_assignment(self, nodes: list, dist_maps: list) -> dict:
        """Assign every graph node to a depot with a regret-based greedy heuristic
        instead of plain nearest-depot. Depots aren't evenly reachable — a centrally
        located depot can dominate the nearest-depot vote for most of the network
        while an edge-of-map depot barely wins any nodes. This caps each depot's
        partition near an even share, prioritizing nodes with the strongest single
        preference (nearest vs. second-nearest) so only genuinely flexible nodes get
        pushed to their non-nearest depot."""
        num_depots = len(dist_maps)
        target_capacity = math.ceil(len(nodes) / num_depots * BALANCE_SLACK)

        preferences = [
            sorted(range(num_depots), key=lambda i: dist_maps[i].get(node, float("inf")))
            for node in nodes
        ]

        def regret(idx):
            prefs = preferences[idx]
            node = nodes[idx]
            best = dist_maps[prefs[0]].get(node, float("inf"))
            second = dist_maps[prefs[1]].get(node, float("inf"))
            return second - best

        order = sorted(range(len(nodes)), key=regret, reverse=True)

        assignment = {}
        counts = [0] * num_depots
        for idx in order:
            node = nodes[idx]
            for depot_i in preferences[idx]:
                if counts[depot_i] < target_capacity:
                    assignment[node] = depot_i
                    counts[depot_i] += 1
                    break
            else:
                depot_i = preferences[idx][0]
                assignment[node] = depot_i
                counts[depot_i] += 1

        return assignment

    def _init_vehicles(self):
        self.vehicles.clear()
        vid = 0
        for depot_index, depot in enumerate(self.depots):
            for _ in range(depot.van_count):
                vid += 1
                self.vehicles[vid] = Vehicle(
                    id=vid,
                    depot_node=depot.node,
                    depot_index=depot_index,
                    current_node=depot.node,
                    lat=depot.lat,
                    lon=depot.lon,
                )

    def reset(self):
        self._init_vehicles()
        self.orders.clear()
        for depot in self.depots:
            depot.restock_until_tick = None
            depot.waitlist = []
            depot.orders_handled_total = 0
            depot.waitlist_events = 0
        self.completed_deliveries = 0
        self.sla_within_threshold = 0
        self.response_times_sec.clear()
        self.recent_deliveries.clear()
        self.delivery_log.clear()
        self.completion_ticks.clear()
        self.bulk_queue_remaining = 0
        self.tick_count = 0
        traffic.update_traffic(self.graph, 0)

    def nearest_depot_index(self, node: int) -> int:
        """The node's assigned depot from the balanced partition (usually its nearest
        depot, but capacity-shifted onto its next-best choice where needed)."""
        return self._node_depot_assignment.get(node, 0)

    def active_order_count(self, depot_index: int) -> int:
        """Orders this depot currently has in flight (not yet completed, not waitlisted)."""
        return sum(
            1
            for o in self.orders.values()
            if o.home_depot_index == depot_index and o.status in ("pending", "assigned")
        )

    def _route_new_order(self, order: Order):
        """Accept the order into its home depot's active pipeline, or waitlist it if the
        depot is over its batch capacity / mid-restock — the logistics constraint."""
        depot = self.depots[order.home_depot_index]
        if depot.is_restocking(self.tick_count):
            order.status = "waitlisted"
            depot.waitlist.append(order.id)
            return

        if self.active_order_count(order.home_depot_index) >= DEPOT_BATCH_CAPACITY:
            order.status = "waitlisted"
            depot.waitlist.append(order.id)
            depot.restock_until_tick = self.tick_count + RESTOCK_TICKS
            depot.waitlist_events += 1
            return

        order.status = "pending"
        depot.orders_handled_total += 1

    def new_order(self, lat: float, lon: float) -> Order:
        node = nearest_node(self.graph, lat, lon)
        node_lat, node_lon = node_lat_lon(self.graph, node)
        order = Order(
            id=f"ORD-{next(self._order_seq)}",
            node=node,
            lat=node_lat,
            lon=node_lon,
            home_depot_index=self.nearest_depot_index(node),
            created_tick=self.tick_count,
        )
        self.orders[order.id] = order
        self._route_new_order(order)
        return order

    def new_random_order(self) -> Order:
        node = random.choice(list(self.graph.nodes))
        lat, lon = node_lat_lon(self.graph, node)
        return self.new_order(lat, lon)

    def drain_waitlists(self):
        """Release waitlisted orders back into the active pipeline as capacity frees up
        (either because a restock finished, or because vans completed deliveries)."""
        for depot in self.depots:
            if depot.is_restocking(self.tick_count):
                continue
            depot.restock_until_tick = None
            active = self.active_order_count(depot.index)
            while depot.waitlist and active < DEPOT_BATCH_CAPACITY:
                order_id = depot.waitlist.pop(0)
                order = self.orders.get(order_id)
                if order is not None and order.status == "waitlisted":
                    order.status = "pending"
                    depot.orders_handled_total += 1
                    active += 1

    def pending_orders(self) -> list[Order]:
        return [o for o in self.orders.values() if o.status == "pending"]

    def pending_orders_for_depot(self, depot_index: int) -> list[Order]:
        return [
            o for o in self.orders.values() if o.status == "pending" and o.home_depot_index == depot_index
        ]

    def idle_vehicles(self) -> list[Vehicle]:
        return [v for v in self.vehicles.values() if v.status == "idle"]

    def idle_vehicles_for_depot(self, depot_index: int) -> list[Vehicle]:
        return [v for v in self.vehicles.values() if v.status == "idle" and v.depot_index == depot_index]

    def completion_rate_per_sec(self) -> float:
        """Deliveries/sec, estimated from the last COMPLETION_WINDOW completions."""
        if len(self.completion_ticks) < 2:
            return 0.0
        newest = self.completion_ticks[-1]
        if self.tick_count - newest > STALE_RATE_TICKS:
            return 0.0  # nothing has finished recently; don't extrapolate from old data
        span = newest - self.completion_ticks[0]
        return (len(self.completion_ticks) - 1) / span if span > 0 else 0.0

    def depot_fuel_cost(self, depot_index: int) -> float:
        km = sum(v.lifetime_distance_m for v in self.vehicles.values() if v.depot_index == depot_index) / 1000.0
        return km * FUEL_CHARGE_PER_KM

    def total_fixed_cost(self) -> float:
        return sum(d.fixed_cost() for d in self.depots)

    def total_variable_cost(self) -> float:
        return sum(self.depot_fuel_cost(d.index) + d.refill_cost() for d in self.depots)

    def depots_payload(self) -> list[dict]:
        payload = []
        for d in self.depots:
            fuel_cost = self.depot_fuel_cost(d.index)
            refill_cost = d.refill_cost()
            fixed_cost = d.fixed_cost()
            payload.append({
                "index": d.index,
                "node": d.node,
                "lat": d.lat,
                "lon": d.lon,
                "name": d.name,
                "vans_originated": d.van_count,
                "orders_handled_total": d.orders_handled_total,
                "active_orders": self.active_order_count(d.index),
                "waitlist_length": len(d.waitlist),
                "waitlist_events": d.waitlist_events,
                "is_restocking": d.is_restocking(self.tick_count),
                "restock_remaining_sec": (
                    max(0, d.restock_until_tick - self.tick_count) if d.is_restocking(self.tick_count) else 0
                ),
                "fixed_cost": round(fixed_cost, 2),
                "fuel_cost": round(fuel_cost, 2),
                "refill_cost": round(refill_cost, 2),
                "variable_cost": round(fuel_cost + refill_cost, 2),
                "total_cost": round(fixed_cost + fuel_cost + refill_cost, 2),
            })
        return payload

    def metrics(self) -> dict:
        avg_response_sec = (
            sum(self.response_times_sec) / len(self.response_times_sec)
            if self.response_times_sec
            else 0.0
        )
        sla_pct = (
            round(100 * self.sla_within_threshold / self.completed_deliveries, 1)
            if self.completed_deliveries
            else 100.0
        )

        backlog_remaining = (len(self.orders) - self.completed_deliveries) + self.bulk_queue_remaining
        rate = self.completion_rate_per_sec()
        if backlog_remaining <= 0:
            eta_sec = 0
        elif rate > 0:
            eta_sec = round(backlog_remaining / rate)
        else:
            eta_sec = None

        fixed_cost = self.total_fixed_cost()
        variable_cost = self.total_variable_cost()

        return {
            "avg_response_time_min": round(avg_response_sec / 60.0, 2),
            "active_dispatches": sum(1 for v in self.vehicles.values() if v.status == "en_route"),
            "returning_count": sum(1 for v in self.vehicles.values() if v.status == "returning"),
            "idle_fleet_count": sum(1 for v in self.vehicles.values() if v.status == "idle"),
            "total_vehicles": len(self.vehicles),
            "total_depots": len(self.depots),
            "sla_threshold_sec": SLA_THRESHOLD_SEC,
            "total_completed_deliveries": self.completed_deliveries,
            "pending_orders": len(self.pending_orders()),
            "waitlisted_orders": sum(1 for o in self.orders.values() if o.status == "waitlisted"),
            "queued_orders": self.bulk_queue_remaining,
            "tick": self.tick_count,
            "avg_congestion": round(traffic.average_congestion(self.graph), 2),
            "sla_pct": sla_pct,
            "backlog_remaining": backlog_remaining,
            "eta_sec": eta_sec,
            "completion_rate_per_min": round(rate * 60, 1),
            "total_fixed_cost": round(fixed_cost, 2),
            "total_variable_cost": round(variable_cost, 2),
            "total_cost_of_operation": round(fixed_cost + variable_cost, 2),
        }
