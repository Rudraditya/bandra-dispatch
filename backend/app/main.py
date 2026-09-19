"""FastAPI application: REST endpoints + WebSocket stream for the dispatch simulation."""
import random
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import traffic
from app.graph_setup import node_lat_lon
from app.simulation import SimulationEngine
from app.state import SimulationState

MAX_BULK_ORDERS = 300
TRAFFIC_SEGMENTS = 40

state = SimulationState()
connections: set[WebSocket] = set()


async def broadcast(sim_state: SimulationState):
    if not connections:
        return
    payload = {
        "tick": sim_state.tick_count,
        "vehicles": [v.to_dict() for v in sim_state.vehicles.values()],
        "orders": [o.to_dict() for o in sim_state.orders.values() if o.status != "completed"],
        "metrics": sim_state.metrics(),
        "traffic": traffic.top_congested_segments(sim_state.graph, k=TRAFFIC_SEGMENTS),
        "recent_deliveries": list(sim_state.recent_deliveries),
    }
    dead = []
    for ws in connections:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connections.discard(ws)


engine = SimulationEngine(state, broadcast)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine.start()
    yield
    await engine.stop()


app = FastAPI(title="Vehicle Routing & Dispatch Simulator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OrderRequest(BaseModel):
    lat: float
    lon: float


class BulkOrderRequest(BaseModel):
    count: int = 100


@app.get("/api/state")
def get_state():
    return {
        "depots": state.depots_payload(),
        "vehicles": [v.to_dict() for v in state.vehicles.values()],
        "orders": [o.to_dict() for o in state.orders.values() if o.status not in ("completed",)],
        "metrics": state.metrics(),
        "traffic": traffic.top_congested_segments(state.graph, k=TRAFFIC_SEGMENTS),
        "recent_deliveries": list(state.recent_deliveries),
    }


@app.get("/api/metrics")
def get_metrics():
    return state.metrics()


@app.get("/api/deliveries")
def get_deliveries():
    return {"deliveries": list(state.delivery_log)}


@app.get("/api/depots")
def get_depots():
    return {"depots": state.depots_payload()}


@app.post("/api/reset")
def reset():
    state.reset()
    return {"status": "ok"}


@app.post("/api/orders")
def create_order(req: OrderRequest):
    order = state.new_order(req.lat, req.lon)
    return order.to_dict()


@app.post("/api/orders/mock")
def create_mock_order():
    node = random.choice(list(state.graph.nodes))
    lat, lon = node_lat_lon(state.graph, node)
    order = state.new_order(lat, lon)
    return order.to_dict()


@app.post("/api/orders/bulk")
def create_bulk_mock_orders(req: BulkOrderRequest):
    """Queue many orders for a stress test — they trickle in one per tick rather
    than landing on the dispatcher all at once."""
    count = max(1, min(req.count, MAX_BULK_ORDERS))
    state.bulk_queue_remaining += count
    return {"queued": count, "total_queued": state.bulk_queue_remaining}


@app.websocket("/ws/simulation")
async def ws_simulation(websocket: WebSocket):
    await websocket.accept()
    connections.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connections.discard(websocket)
    finally:
        connections.discard(websocket)
