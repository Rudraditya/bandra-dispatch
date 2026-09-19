import { useState } from "react";
import Sidebar from "../components/Sidebar";
import MapView from "../components/MapView";

export default function DashboardPage() {
  const [dropMode, setDropMode] = useState(false);

  return (
    <div className="flex flex-1 overflow-hidden">
      <Sidebar dropMode={dropMode} onToggleDropMode={() => setDropMode((v) => !v)} />
      <main className="relative flex-1">
        <MapView dropMode={dropMode} />
      </main>
    </div>
  );
}
