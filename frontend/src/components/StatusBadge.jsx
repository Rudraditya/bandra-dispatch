export default function StatusBadge({ icon: Icon, label, statusLabel, color, suffix }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
      <div className="flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5 shrink-0" style={{ color }} />
        <span className="truncate text-[11px] font-medium uppercase tracking-wide text-slate-400">
          {label}
        </span>
      </div>
      <div className="mt-1.5 flex items-center gap-1.5">
        <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
        <span className="truncate text-sm font-semibold text-slate-100">{statusLabel}</span>
      </div>
      {suffix && <p className="mt-0.5 truncate text-[10px] text-slate-500">{suffix}</p>}
    </div>
  );
}
