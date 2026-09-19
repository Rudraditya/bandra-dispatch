"""Vehicle-to-order assignment: orders are partitioned to their nearest depot (the
logistics constraint), then within each depot the Hungarian algorithm optimally
matches that depot's idle vans to that depot's pending orders."""
import networkx as nx
import numpy as np
from scipy.optimize import linear_sum_assignment

from app.routing import path_cumulative_distance
from app.state import SimulationState

UNREACHABLE_COST = 1e9


def dispatch_orders(state: SimulationState) -> list[tuple[int, str]]:
    assignments = []

    for depot in state.depots:
        idle = state.idle_vehicles_for_depot(depot.index)
        pending = state.pending_orders_for_depot(depot.index)
        if not idle or not pending:
            continue

        # Idle vans at a depot always share the same current_node (the depot itself,
        # since vans return home between deliveries) — one Dijkstra run per depot
        # gives distances/paths to every pending order in that depot's queue.
        distances, paths = nx.single_source_dijkstra(state.graph, depot.node, weight="current_weight")

        cost_matrix = np.full((len(idle), len(pending)), UNREACHABLE_COST)
        routes: dict[int, list[int]] = {}
        for j, order in enumerate(pending):
            if order.node in distances:
                cost_matrix[:, j] = distances[order.node]
                routes[j] = paths[order.node]

        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        for i, j in zip(row_ind, col_ind):
            if cost_matrix[i, j] >= UNREACHABLE_COST:
                continue  # no valid path; leave both unassigned this tick

            vehicle = idle[i]
            order = pending[j]
            path = routes[j]

            vehicle.status = "en_route"
            vehicle.target_order_id = order.id
            vehicle.route_path = path
            vehicle.route_cum_dist = path_cumulative_distance(state.graph, path)
            vehicle.route_total_m = vehicle.route_cum_dist[-1]
            vehicle.route_progress_m = 0.0

            order.status = "assigned"
            order.assigned_vehicle_id = vehicle.id

            assignments.append((vehicle.id, order.id))

    return assignments
