"""Lightweight simulated traffic: per-edge congestion that oscillates over time,
feeding both the dispatch cost matrix and a live map overlay."""
import math

from app.graph_setup import node_lat_lon

MAX_MULTIPLIER = 2.6


def init_traffic(graph):
    """Give every edge a stable random profile (how jam-prone it is, and when)."""
    for u, v, k, data in graph.edges(keys=True, data=True):
        seed = (hash((u, v, k)) % 10_000) / 10_000
        data["base_intensity"] = 0.25 + 0.75 * seed  # every road has *some* baseline traffic
        data["phase"] = seed * 2 * math.pi
        data["current_weight"] = data.get("travel_time", 1.0)
        data["congestion"] = 1.0


def update_traffic(graph, tick: int):
    """Advance the congestion wave for every edge to the current tick."""
    for _, _, _, data in graph.edges(keys=True, data=True):
        wave = 0.5 + 0.5 * math.sin(tick / 45.0 + data["phase"])
        multiplier = 1.0 + data["base_intensity"] * (MAX_MULTIPLIER - 1.0) * wave
        data["congestion"] = multiplier
        data["current_weight"] = data.get("travel_time", 1.0) * multiplier


def edge_congestion(graph, u, v) -> float:
    data = graph.get_edge_data(u, v)
    if not data:
        return 1.0
    return min(d.get("congestion", 1.0) for d in data.values())


def average_congestion(graph) -> float:
    values = [data["congestion"] for _, _, data in graph.edges(data=True)]
    return sum(values) / len(values) if values else 1.0


def top_congested_segments(graph, k: int = 40):
    """The k most jammed road segments right now, as map-ready polylines."""
    edges = list(graph.edges(keys=True, data=True))
    edges.sort(key=lambda e: e[3]["congestion"], reverse=True)

    segments = []
    for u, v, _, data in edges[:k]:
        lat1, lon1 = node_lat_lon(graph, u)
        lat2, lon2 = node_lat_lon(graph, v)
        level = min(1.0, (data["congestion"] - 1.0) / (MAX_MULTIPLIER - 1.0))
        segments.append({"path": [[lat1, lon1], [lat2, lon2]], "level": round(level, 2)})
    return segments
