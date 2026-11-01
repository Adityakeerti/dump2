import { useEffect, useState } from "react";
import { Sidebar, Topbar } from "./components/Shell.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import PolicyLab from "./pages/PolicyLab.jsx";
import Residents from "./pages/Residents.jsx";
import Civic from "./pages/Civic.jsx";
import { Messages, Tickets, TownHall } from "./pages/Services.jsx";
import { useTwin } from "./lib/useTwin.js";
import { usePoll } from "./lib/usePoll.js";
import { agentEvents, getJSON } from "./lib/api.js";

function readTheme() {
  try { return localStorage.getItem("cs-theme") || "auto"; } catch { return "auto"; }
}

export default function App() {
  const [page, setPage] = useState(() => location.hash.slice(1) || "dashboard");
  const [theme, setThemeState] = useState(readTheme);
  const [query, setQuery] = useState("");
  const [seenEvents, setSeenEvents] = useState(0);

  useEffect(() => {
    const onHash = () => setPage(location.hash.slice(1) || "dashboard");
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);
  const go = (p) => { location.hash = p; setPage(p); };

  useEffect(() => {
    if (theme === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
  }, [theme]);
  const setTheme = (t) => { setThemeState(t); try { localStorage.setItem("cs-theme", t); } catch { /* storage blocked */ } };
  const effectiveTheme = theme === "auto" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : theme;

  const twin = useTwin();
  const cityHealth = usePoll(() => getJSON("/api/city/health"), 2000);
  const cityClusters = usePoll(() => getJSON("/api/city/clusters"), 2500);
  const cityTraces = usePoll(() => getJSON("/api/city/traces?limit=80"), 3000);
  const complaints = usePoll(() => getJSON("/api/complaint-flow/feed"), 5000);
  const missions = usePoll(() => getJSON("/api/emergency/missions"), 5000);
  const incidents = usePoll(() => getJSON("/api/emergency/incidents?limit=20"), 5000);
  const agent = usePoll(() => agentEvents(0), 4000);
  const civic = usePoll(() => getJSON("/api/civic/health"), 5000);

  const city = { health: cityHealth.data, clusters: cityClusters.data, traces: cityTraces.data, error: cityHealth.error };
  const state = twin.state;
  const services = [
    { name: "Twin", state: twin.connected ? (state?.status === "running" ? "up" : "warn") : "down", detail: "CTM digital twin + RL (8003)" },
    { name: "Gemma agents", state: cityHealth.data ? (cityHealth.data.llm_server ? "up" : "warn") : "down", detail: cityHealth.data ? `llama-server ${cityHealth.data.llm_server ? "online" : "offline"}` : cityHealth.error },
    { name: "Complaints", state: complaints.data ? "up" : "down", detail: complaints.error || "port 8001" },
    { name: "Emergency", state: missions.data ? "up" : "down", detail: missions.error || "port 8002" },
    { name: "Civic sim", state: civic.data ? (civic.data.rl_loaded ? "up" : "warn") : "down", detail: civic.data ? `port 8005 · ${civic.data.policy} policy` : civic.error },
    { name: "Voice agent", state: agent.data ? "up" : "down", detail: agent.error || "port 8000" },
  ];
  const lastEventId = twin.events.at(-1)?.id || 0;
  const unread = twin.events.filter((e) => e.id > seenEvents && ["congestion", "disruption", "rl"].includes(e.category)).length;

  const recentIncidents = [...(missions.data?.missions || []).slice(0, 10), ...(incidents.data?.incidents || [])];

  return (
    <div className="shell">
      <div className="app">
        <Sidebar page={page} setPage={go} />
        <main className="main">
          <Topbar theme={effectiveTheme} setTheme={setTheme} services={services} unread={unread}
            onBell={() => { setSeenEvents(lastEventId); go("dashboard"); }} query={query} setQuery={setQuery} />
          {page === "dashboard" && <Dashboard twin={twin} city={city} complaints={complaints.data?.complaints} incidents={recentIncidents} query={query} theme={effectiveTheme} />}
          {page === "policy" && <PolicyLab twin={twin} />}
          {page === "residents" && <Residents city={city} />}
          {page === "civic" && <Civic theme={effectiveTheme} query={query} />}
          {page === "townhall" && <TownHall feed={complaints.data} error={complaints.error} />}
          {page === "tickets" && <Tickets missions={missions.data} incidents={incidents.data} error={missions.error} />}
          {page === "messages" && <Messages events={agent.data?.events} error={agent.error} />}
        </main>
      </div>
    </div>
  );
}
