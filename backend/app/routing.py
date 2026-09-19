"""Real-world path geometry: cumulative distance and per-edge speed, used to move
vehicles continuously along their route at an actual driving speed rather than
jumping node-to-node."""

DEFAULT_SPEED_KPH = 30.0
DEFAULT_EDGE_LENGTH_M = 50.0


def path_cumulative_distance(graph, path: list[int]) -> list[float]:
    """Cumulative real-world distance (meters) at each node along `path`."""
    cum = [0.0]
    for u, v in zip(path[:-1], path[1:]):
        data = graph.get_edge_data(u, v)
        length = (
            min(d.get("length", DEFAULT_EDGE_LENGTH_M) for d in data.values())
            if data
            else DEFAULT_EDGE_LENGTH_M
        )
        cum.append(cum[-1] + length)
    return cum


def edge_speed_kph(graph, u, v) -> float:
    data = graph.get_edge_data(u, v)
    if not data:
        return DEFAULT_SPEED_KPH
    return min(d.get("speed_kph", DEFAULT_SPEED_KPH) for d in data.values())
