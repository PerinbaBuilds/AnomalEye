import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import AgentConsole from "./pages/AgentConsole";
import Alerts from "./pages/Alerts";
import Entity360 from "./pages/Entity360";
import LiveMonitor from "./pages/LiveMonitor";
import NetworkPage from "./pages/NetworkPage";
import Performance from "./pages/Performance";
import Methodology from "./pages/Methodology";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/agent" element={<AgentConsole />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/monitor" element={<LiveMonitor />} />
        <Route path="/network" element={<NetworkPage />} />
        <Route path="/entity/:id" element={<Entity360 />} />
        <Route path="/performance" element={<Performance />} />
        <Route path="/methodology" element={<Methodology />} />
      </Routes>
    </Layout>
  );
}
