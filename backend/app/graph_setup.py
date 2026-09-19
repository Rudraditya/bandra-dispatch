"""Street network loading, caching, and depot extraction for the Bandra simulation area."""
import os

import networkx as nx
import osmnx as ox

PLACE_NAME = "Bandra, Mumbai, India"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
GRAPH_PATH = os.path.join(DATA_DIR, "bandra_mumbai.graphml")

NUM_DEPOTS = 7


def load_graph() -> nx.MultiDiGraph:
    """Load the drivable street network for Bandra, Mumbai, caching it to disk as GraphML."""
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(GRAPH_PATH):
        graph = ox.load_graphml(GRAPH_PATH)
    else:
        graph = ox.graph_from_place(PLACE_NAME, network_type="drive")
        graph = ox.add_edge_speeds(graph)
        graph = ox.add_edge_travel_times(graph)
        ox.save_graphml(graph, GRAPH_PATH)

    # GraphML round-trips edge attributes as strings; make sure they're numeric.
    for _, _, data in graph.edges(data=True):
        if "travel_time" in data:
            data["travel_time"] = float(data["travel_time"])
        if "length" in data:
            data["length"] = float(data["length"])
        if "speed_kph" in data:
            data["speed_kph"] = float(data["speed_kph"])

    return graph


def pick_depot_nodes(graph: nx.MultiDiGraph, count: int = NUM_DEPOTS) -> list[int]:
    """Pick `count` well-distributed nodes across the graph to serve as static depots.

    Uses greedy farthest-point sampling on real *road-network travel time*, not
    straight-line lat/lon — a depot's true "reach" depends on the street layout
    (dead ends, one-ways, the coastline), so two points can look evenly spread on a
    map while one sits in a network backwater the other's roads dominate. Seeding
    from the graph metric instead means the resulting depots actually split the
    network evenly, not just the page.
    """
    nodes = list(graph.nodes)
    if len(nodes) <= count:
        return nodes

    # Anchor the search at a well-connected node (a major intersection) rather than
    # an arbitrary/random one, so placement is deterministic and reproducible.
    start = max(nodes, key=lambda n: graph.out_degree(n))
    chosen = [start]

    min_dist_to_chosen = {
        n: d for n, d in nx.single_source_dijkstra_path_length(graph, start, weight="travel_time").items()
    }
    for n in nodes:
        min_dist_to_chosen.setdefault(n, float("inf"))

    while len(chosen) < count:
        # The node currently farthest (by travel time) from every depot chosen so
        # far is the best next depot — classic max-min farthest-point sampling.
        next_node = max(nodes, key=lambda n: -1 if n in chosen else min_dist_to_chosen[n])
        chosen.append(next_node)

        new_dist = nx.single_source_dijkstra_path_length(graph, next_node, weight="travel_time")
        for n in nodes:
            d = new_dist.get(n, float("inf"))
            if d < min_dist_to_chosen[n]:
                min_dist_to_chosen[n] = d

    return chosen


def node_lat_lon(graph: nx.MultiDiGraph, node_id: int) -> tuple[float, float]:
    data = graph.nodes[node_id]
    return data["y"], data["x"]


def nearest_node(graph: nx.MultiDiGraph, lat: float, lon: float) -> int:
    return ox.distance.nearest_nodes(graph, X=lon, Y=lat)
