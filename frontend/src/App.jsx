import { useState } from "react";
import { SimulationProvider } from "./context/SimulationContext";
import TabBar from "./components/TabBar";
import DashboardPage from "./pages/DashboardPage";
import DeliveryLogPage from "./pages/DeliveryLogPage";
import DepotAnalyticsPage from "./pages/DepotAnalyticsPage";

function App() {
  const [tab, setTab] = useState("dashboard");

  return (
    <SimulationProvider>
      <div className="flex h-screen w-screen flex-col overflow-hidden bg-slate-950">
        <TabBar active={tab} onChange={setTab} />
        {tab === "dashboard" && <DashboardPage />}
        {tab === "deliveries" && <DeliveryLogPage />}
        {tab === "depots" && <DepotAnalyticsPage />}
      </div>
    </SimulationProvider>
  );
}

export default App;
