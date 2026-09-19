import {
  Gauge,
  Truck,
  ParkingCircle,
  PackageCheck,
  Hourglass,
  Undo2,
  Zap,
  Flame,
  MousePointerClick,
  RotateCcw,
  Wifi,
  WifiOff,
  TrafficCone,
  Timer,
} from "lucide-react";
import MetricCard from "./MetricCard";
import StatusBadge from "./StatusBadge";
import BacklogStatus from "./BacklogStatus";
import { useSimulation } from "../context/SimulationContext";

const STRESS_TEST_BATCHES = [100, 200, 300];

function trafficStatus(avgCongestion) {
  if (avgCongestion < 1.3) return { label: "Light", color: "#0ca30c" };
  if (avgCongestion < 1.8) return { label: "Moderate", color: "#fab219" };
  if (avgCongestion < 2.2) return { label: "Heavy", color: "#ec835a" };
  return { label: "Severe", color: "#d03b3b" };
}

function slaStatus(pct) {
  if (pct >= 95) return { label: "On Target", color: "#0ca30c" };
  if (pct >= 80) return { label: "At Risk", color: "#fab219" };
  if (pct >= 60) return { label: "Slipping", color: "#ec835a" };
  return { label: "Breached", color: "#d03b3b" };
}

export default function Sidebar({ dropMode, onToggleDropMode }) {
  const { metrics, connected, triggerMockOrder, triggerBulkOrders, reset } = useSimulation();

  const traffic = trafficStatus(metrics.avg_congestion ?? 1);
  const sla = slaStatus(metrics.sla_pct ?? 100);

  return (
    <aside className="thin-scroll flex h-full w-80 flex-shrink-0 flex-col gap-5 overflow-y-auto border-r border-slate-800 bg-slate-950/90 p-5">
      <div>
        <p className="text-xs text-slate-400">Live vehicle routing &amp; dispatch simulator</p>
        <div className="mt-2 flex items-center gap-1.5 text-xs">
          {connected ? (
            <Wifi className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <WifiOff className="h-3.5 w-3.5 text-rose-400" />
          )}
          <span className={connected ? "text-emerald-400" : "text-rose-400"}>
            {connected ? "Live" : "Reconnecting…"}
          </span>
          <span className="ml-auto text-slate-500">t+{metrics.tick}s</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <MetricCard
          icon={Gauge}
          label="Avg Response (min)"
          value={metrics.avg_response_time_min}
          accent="text-cyan-400"
        />
        <MetricCard
          icon={Truck}
          label="Active"
          value={metrics.active_dispatches}
          accent="text-amber-400"
        />
        <MetricCard
          icon={Undo2}
          label="Returning"
          value={metrics.returning_count ?? 0}
          accent="text-sky-400"
        />
        <MetricCard
          icon={ParkingCircle}
          label="Idle Fleet"
          value={metrics.idle_fleet_count}
          accent="text-slate-400"
        />
        <MetricCard
          icon={PackageCheck}
          label="Completed"
          value={metrics.total_completed_deliveries}
          accent="text-emerald-400"
        />
        <MetricCard
          icon={Hourglass}
          label="Waitlisted"
          value={metrics.waitlisted_orders ?? 0}
          accent="text-orange-400"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <StatusBadge
          icon={TrafficCone}
          label="Traffic"
          statusLabel={traffic.label}
          color={traffic.color}
          suffix={`${(metrics.avg_congestion ?? 1).toFixed(2)}x avg`}
        />
        <StatusBadge
          icon={Timer}
          label={`SLA (${Math.round((metrics.sla_threshold_sec ?? 1080) / 60)} min)`}
          statusLabel={sla.label}
          color={sla.color}
          suffix={`${metrics.sla_pct ?? 100}% on time`}
        />
      </div>

      <div className="flex flex-col gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Controls
        </h2>

        <button
          onClick={triggerMockOrder}
          className="flex items-center justify-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-4 py-2.5 text-sm font-medium text-cyan-300 transition-colors hover:bg-cyan-500/20"
        >
          <Zap className="h-4 w-4" />
          Trigger Mock Order
        </button>

        <button
          onClick={onToggleDropMode}
          className={`flex items-center justify-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors ${
            dropMode
              ? "border-amber-500/40 bg-amber-500/20 text-amber-300"
              : "border-slate-700 bg-slate-800/40 text-slate-300 hover:bg-slate-800"
          }`}
        >
          <MousePointerClick className="h-4 w-4" />
          {dropMode ? "Drop Mode: ON — click map" : "Interactive Drop Mode"}
        </button>

        <button
          onClick={reset}
          className="flex items-center justify-center gap-2 rounded-lg border border-slate-700 bg-slate-800/40 px-4 py-2.5 text-sm font-medium text-slate-300 transition-colors hover:border-rose-500/30 hover:bg-rose-500/10 hover:text-rose-300"
        >
          <RotateCcw className="h-4 w-4" />
          Reset Simulation
        </button>
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <Flame className="h-3.5 w-3.5 text-orange-400" />
          Stress Test
        </h2>
        <div className="grid grid-cols-3 gap-2">
          {STRESS_TEST_BATCHES.map((count) => (
            <button
              key={count}
              onClick={() => triggerBulkOrders(count)}
              className="rounded-lg border border-orange-500/30 bg-orange-500/10 py-2 text-sm font-medium text-orange-300 transition-colors hover:bg-orange-500/20"
            >
              +{count}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-slate-500">
          Orders trickle in one per second — a sustained load test, not an instant burst.
        </p>
        <BacklogStatus metrics={metrics} />
      </div>

      <div className="mt-auto rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-500">
        <p>
          Pending orders: <span className="text-slate-300">{metrics.pending_orders}</span>
        </p>
        <p className="mt-1">
          {metrics.total_vehicles ?? "—"} vans · {metrics.total_depots ?? "—"} depots · 1 tick = 1
          real second · {Math.round((metrics.sla_threshold_sec ?? 1080) / 60)} min SLA target
        </p>
        <p className="mt-1">
          See <span className="text-slate-300">Delivery Log</span> and{" "}
          <span className="text-slate-300">Depot Analytics</span> tabs for details.
        </p>
      </div>
    </aside>
  );
}
