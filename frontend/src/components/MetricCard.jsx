export default function MetricCard({ icon: Icon, label, value, accent }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 backdrop-blur">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
          {label}
        </span>
        {Icon && <Icon className={`h-4 w-4 ${accent ?? "text-slate-500"}`} />}
      </div>
      <p className="mt-2 text-2xl font-semibold text-slate-50">{value}</p>
    </div>
  );
}
