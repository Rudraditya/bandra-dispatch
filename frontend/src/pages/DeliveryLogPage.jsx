import { useEffect, useMemo, useState } from "react";
import { RefreshCw, ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";
import { API_BASE } from "../lib/api";

const REFRESH_MS = 5000;

const COLUMNS = [
  { key: "order_id", label: "Order" },
  { key: "vehicle_id", label: "Vehicle" },
  { key: "origin_depot", label: "Origin Depot" },
  { key: "duration_s", label: "Duration" },
  { key: "distance_m", label: "Distance" },
  { key: "fuel_cost", label: "Fuel Cost (₹)" },
  { key: "completed_tick", label: "Completed @" },
];

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatDistance(meters) {
  return meters >= 1000 ? `${(meters / 1000).toFixed(2)} km` : `${Math.round(meters)} m`;
}

export default function DeliveryLogPage() {
  const [deliveries, setDeliveries] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [sortKey, setSortKey] = useState("completed_tick");
  const [sortDir, setSortDir] = useState("desc");
  const [depotFilter, setDepotFilter] = useState("all");
  const [vehicleFilter, setVehicleFilter] = useState("");
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([
      fetch(`${API_BASE}/api/deliveries`).then((r) => r.json()),
      fetch(`${API_BASE}/api/metrics`).then((r) => r.json()),
    ])
      .then(([d, m]) => {
        setDeliveries(d.deliveries ?? []);
        setMetrics(m);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, []);

  const depotNames = useMemo(
    () => [...new Set(deliveries.map((d) => d.origin_depot))].sort(),
    [deliveries]
  );

  const rows = useMemo(() => {
    let filtered = deliveries;
    if (depotFilter !== "all") filtered = filtered.filter((d) => d.origin_depot === depotFilter);
    if (vehicleFilter.trim()) {
      const needle = vehicleFilter.trim().toLowerCase();
      filtered = filtered.filter(
        (d) =>
          String(d.vehicle_id).includes(needle) || d.order_id.toLowerCase().includes(needle)
      );
    }
    const sorted = [...filtered].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "string") return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      return sortDir === "asc" ? av - bv : bv - av;
    });
    return sorted;
  }, [deliveries, depotFilter, vehicleFilter, sortKey, sortDir]);

  const toggleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const totalDistance = rows.reduce((sum, d) => sum + d.distance_m, 0);
  const totalFuel = rows.reduce((sum, d) => sum + d.fuel_cost, 0);

  return (
    <div className="thin-scroll flex flex-1 flex-col overflow-y-auto bg-slate-950 p-6">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-slate-50">Delivery Log</h1>
          <p className="text-xs text-slate-400">
            Every completed delivery — compare vehicles, depots, durations, distance, and fuel cost.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/40 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-slate-800"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryCard label="Deliveries Shown" value={rows.length} />
        <SummaryCard label="Total Distance" value={formatDistance(totalDistance)} />
        <SummaryCard label="Total Fuel Cost" value={`₹${totalFuel.toFixed(2)}`} />
        <SummaryCard
          label="Total Cost of Operation"
          value={metrics ? `₹${metrics.total_cost_of_operation.toFixed(2)}` : "—"}
          accent="text-cyan-400"
        />
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <select
          value={depotFilter}
          onChange={(e) => setDepotFilter(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200"
        >
          <option value="all">All depots</option>
          {depotNames.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <input
          value={vehicleFilter}
          onChange={(e) => setVehicleFilter(e.target.value)}
          placeholder="Search vehicle # or order id…"
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500"
        />
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full min-w-[720px] text-left text-xs">
          <thead className="bg-slate-900/80 text-slate-400">
            <tr>
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  onClick={() => toggleSort(col.key)}
                  className="cursor-pointer select-none whitespace-nowrap px-3 py-2 font-medium uppercase tracking-wide hover:text-slate-200"
                >
                  <span className="flex items-center gap-1">
                    {col.label}
                    {sortKey === col.key ? (
                      sortDir === "asc" ? (
                        <ArrowUp className="h-3 w-3" />
                      ) : (
                        <ArrowDown className="h-3 w-3" />
                      )
                    ) : (
                      <ArrowUpDown className="h-3 w-3 opacity-30" />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr
                key={`${d.order_id}-${d.completed_tick}`}
                className="border-t border-slate-800/60 text-slate-300 hover:bg-slate-900/40"
              >
                <td className="px-3 py-2 font-medium text-slate-200">{d.order_id}</td>
                <td className="px-3 py-2">Van #{d.vehicle_id}</td>
                <td className="px-3 py-2">{d.origin_depot}</td>
                <td className="px-3 py-2 tabular-nums">{formatDuration(d.duration_s)}</td>
                <td className="px-3 py-2 tabular-nums">{formatDistance(d.distance_m)}</td>
                <td className="px-3 py-2 tabular-nums">₹{d.fuel_cost.toFixed(2)}</td>
                <td className="px-3 py-2 tabular-nums text-slate-500">t+{d.completed_tick}s</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="px-3 py-8 text-center text-slate-500">
                  No completed deliveries yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, accent }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${accent ?? "text-slate-50"}`}>{value}</p>
    </div>
  );
}
