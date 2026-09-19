import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { API_BASE, WS_URL } from "../lib/api";

const SimulationContext = createContext(null);

const EMPTY_METRICS = {
  avg_response_time_min: 0,
  active_dispatches: 0,
  idle_fleet_count: 0,
  total_completed_deliveries: 0,
  pending_orders: 0,
  tick: 0,
};

export function SimulationProvider({ children }) {
  const [depots, setDepots] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [orders, setOrders] = useState([]);
  const [metrics, setMetrics] = useState(EMPTY_METRICS);
  const [traffic, setTraffic] = useState([]);
  const [recentDeliveries, setRecentDeliveries] = useState([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/state`)
      .then((r) => r.json())
      .then((data) => {
        setDepots(data.depots);
        setVehicles(data.vehicles);
        setOrders(data.orders);
        setMetrics(data.metrics);
        setTraffic(data.traffic ?? []);
        setRecentDeliveries(data.recent_deliveries ?? []);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;

    function connect() {
      if (cancelled) return;
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        setVehicles(data.vehicles);
        setOrders(data.orders);
        setMetrics(data.metrics);
        setTraffic(data.traffic ?? []);
        setRecentDeliveries(data.recent_deliveries ?? []);
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        if (!cancelled) {
          reconnectTimer.current = setTimeout(connect, 1500);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, []);

  const triggerMockOrder = useCallback(() => {
    fetch(`${API_BASE}/api/orders/mock`, { method: "POST" }).catch(() => {});
  }, []);

  const triggerBulkOrders = useCallback((count) => {
    fetch(`${API_BASE}/api/orders/bulk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ count }),
    }).catch(() => {});
  }, []);

  const dropOrder = useCallback((lat, lon) => {
    fetch(`${API_BASE}/api/orders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat, lon }),
    }).catch(() => {});
  }, []);

  const reset = useCallback(() => {
    fetch(`${API_BASE}/api/reset`, { method: "POST" }).catch(() => {});
  }, []);

  const value = {
    depots,
    vehicles,
    orders,
    metrics,
    traffic,
    recentDeliveries,
    connected,
    triggerMockOrder,
    triggerBulkOrders,
    dropOrder,
    reset,
  };

  return <SimulationContext.Provider value={value}>{children}</SimulationContext.Provider>;
}

export function useSimulation() {
  const ctx = useContext(SimulationContext);
  if (!ctx) throw new Error("useSimulation must be used within SimulationProvider");
  return ctx;
}
