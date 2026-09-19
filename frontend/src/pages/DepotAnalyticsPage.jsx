import { useEffect, useState } from "react";
import { RefreshCw, Hourglass } from "lucide-react";
import { API_BASE } from "../lib/api";

const REFRESH_MS = 5000;

export default function DepotAnalyticsPage() {
  const [depots, setDepots] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([
      fetch(`${API_BASE}/api/depots`).then((r) => r.json()),
      fetch(`${API_BASE}/api/metrics`).then((r) => r.json()),
    ])
      .then(([d, m]) => {
        setDepots(d.depots ?? []);
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

  const totals = depots.reduce(
    (acc, d) => ({
      orders: acc.orders + d.orders_handled_total,
      waitlistEvents: acc.waitlistEvents + d.waitlist_events,
      vans: acc.vans + d.vans_originated,
      fixed: acc.fixed + d.fixed_cost,
      variable: acc.variable + d.variable_cost,
      total: acc.total + d.total_cost,
    }),
    { orders: 0, waitlistEvents: 0, vans: 0, fixed: 0, variable: 0, total: 0 }
  );

  return (
    <div className="thin-scroll flex flex-1 flex-col overflow-y-auto bg-slate-950 p-6">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-slate-50">Depot Analytics</h1>
          <p className="text-xs text-slate-400">
            Orders handled, logistics-constraint waitlisting, fleet origin, and cost per depot.
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

      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <SummaryCard label="Depots" value={depots.length} />
        <SummaryCard label="Total Vans" value={totals.vans} />
        <SummaryCard label="Orders Handled" value={totals.orders} />
        <SummaryCard label="Waitlist Events" value={totals.waitlistEvents} accent="text-amber-400" />
        <SummaryCard label="Fixed Cost" value={`₹${totals.fixed.toFixed(0)}`} />
        <SummaryCard
          label="Total Cost of Operation"
          value={metrics ? `₹${metrics.total_cost_of_operation.toFixed(2)}` : "—"}
          accent="text-cyan-400"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {depots.map((d) => (
          <DepotCard key={d.index} depot={d} />
        ))}
      </div>

      <p className="mt-5 text-[11px] text-slate-500">
        Fixed cost = warehouse ops (₹1,000) + utility (₹100) per depot, plus driver salary (₹500) +
        maintenance (₹60) per van — all one-time, per simulation. Variable cost = fuel (₹100/km,
        including empty return-to-depot trips) + warehouse refill (₹500 per restock event).
      </p>
    </div>
  );
}

function DepotCard({ depot }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-100">{depot.name}</h2>
        {depot.is_restocking && (
          <span className="flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-300">
            <Hourglass className="h-3 w-3" />
            Restocking · {depot.restock_remaining_sec}s
          </span>
        )}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <Stat label="Vans Originated" value={depot.vans_originated} />
        <Stat label="Active Orders" value={`${depot.active_orders} / 60`} />
        <Stat label="Orders Handled" value={depot.orders_handled_total} />
        <Stat label="Waitlisted Now" value={depot.waitlist_length} />
        <Stat label="Waitlist Events" value={depot.waitlist_events} />
      </div>

      <div className="mt-3 space-y-1 border-t border-slate-800 pt-3 text-xs">
        <CostRow label="Fixed cost" value={depot.fixed_cost} />
        <CostRow label="Fuel cost" value={depot.fuel_cost} />
        <CostRow label="Refill cost" value={depot.refill_cost} />
        <CostRow label="Total cost" value={depot.total_cost} bold />
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <p className="text-slate-500">{label}</p>
      <p className="font-medium tabular-nums text-slate-200">{value}</p>
    </div>
  );
}

function CostRow({ label, value, bold }) {
  return (
    <div className="flex items-center justify-between">
      <span className={bold ? "font-medium text-slate-300" : "text-slate-500"}>{label}</span>
      <span className={`tabular-nums ${bold ? "font-semibold text-cyan-400" : "text-slate-300"}`}>
        ₹{value.toFixed(2)}
      </span>
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
