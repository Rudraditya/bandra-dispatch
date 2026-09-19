import { LayoutDashboard, Table2, Warehouse } from "lucide-react";

const TABS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "deliveries", label: "Delivery Log", icon: Table2 },
  { id: "depots", label: "Depot Analytics", icon: Warehouse },
];

export default function TabBar({ active, onChange }) {
  return (
    <nav className="flex h-12 flex-shrink-0 items-center gap-1 border-b border-slate-800 bg-slate-950 px-4">
      <span className="mr-4 text-sm font-semibold tracking-tight text-slate-50">
        Bandra Dispatch
      </span>
      {TABS.map((tab) => {
        const Icon = tab.icon;
        const isActive = active === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              isActive
                ? "bg-cyan-500/15 text-cyan-300"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {tab.label}
          </button>
        );
      })}
    </nav>
  );
}
