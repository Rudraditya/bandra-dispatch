const BAR_COLOR = "#3987e5"; // sequential blue — matches Delivery Times bars

function formatETA(etaSec) {
  if (etaSec == null) return "estimating…";
  if (etaSec <= 0) return "clearing now";
  const m = Math.floor(etaSec / 60);
  const s = Math.round(etaSec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function BacklogStatus({ metrics }) {
  const backlog = metrics.backlog_remaining ?? 0;
  const completed = metrics.total_completed_deliveries ?? 0;
  const total = completed + backlog;

  if (backlog <= 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-500">
        No backlog — dispatch is keeping up in real time.
      </div>
    );
  }

  const pct = total > 0 ? Math.min(100, (completed / total) * 100) : 0;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">
          {completed} / {total} orders
        </span>
        <span className="font-medium tabular-nums text-slate-200">
          ETA {formatETA(metrics.eta_sec)}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 rounded-full bg-slate-800">
        <div className="h-1.5 rounded-full" style={{ width: `${pct}%`, background: BAR_COLOR }} />
      </div>
      <p className="mt-1 text-[10px] text-slate-500">
        {backlog} remaining · {(metrics.completion_rate_per_min ?? 0).toFixed(1)}/min throughput
      </p>
    </div>
  );
}
