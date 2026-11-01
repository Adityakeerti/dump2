import { useMemo, useState } from "react";
import { clusterColor, initials, simClock, wallTime } from "../lib/format.js";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "rl", label: "RL" },
  { id: "congestion", label: "Congestion" },
  { id: "population", label: "Agents" },
  { id: "city", label: "City" },
];

const CATEGORY_FILTER = { rl: "rl", control: "rl", system: "rl", congestion: "congestion", disruption: "congestion", diagnosis: "congestion", population: "population", decision: "rl", complaint: "city", emergency: "city" };
const TONE = { rl: "peach", decision: "peach", congestion: "peach", disruption: "peach", diagnosis: "peach", population: "green", complaint: "green", emergency: "green", control: "grey", system: "grey" };

const TITLE = {
  jam_onset: "Congestion detected", jam_cleared: "Congestion cleared", disruption_start: "Capacity disruption",
  disruption_end: "Capacity restored", trips_planned: "Agent travel plan", episode_complete: "Episode complete",
  episode_start: "New episode", policy_changed: "View switched", scenario_changed: "Scenario changed",
  episode_reset: "Episode reset", root_cause_traced: "Root cause traced", learning_toggled: "Learning mode", twin_started: "Twin online",
};

// Right-hand "City Activity" column: week strip, on-duty agents, merged live timeline.
export default function ActivityPanel({ events, decisions, clusters, complaints, incidents, query, simTime }) {
  const [filter, setFilter] = useState("all");
  const today = new Date();
  const days = Array.from({ length: 7 }, (_, i) => new Date(today.getFullYear(), today.getMonth(), today.getDate() + i - 3));
  const clusterIdx = Object.fromEntries((clusters || []).map((c, i) => [c.id, i]));

  const items = useMemo(() => {
    const out = [];
    for (const e of events) {
      out.push({ key: `e${e.id}`, ts: e.ts, sim: e.sim_time, cat: e.category, title: TITLE[e.kind] || e.kind, text: e.text, who: e.cluster_id });
    }
    // Decisions are frequent: "All" shows only recent phase switches; the RL filter adds shield holds.
    const ds = filter === "rl" ? decisions.filter((d) => d.switched || d.shield).slice(-40) : decisions.filter((d) => d.switched).slice(-6);
    for (const d of ds) {
      out.push({
        key: `d${d.id}`, ts: d.ts, sim: d.sim_time, cat: "decision",
        title: `J${d.junction + 1} ${d.switched ? "phase switch" : "shield hold"} · ${d.mode}`, text: d.text, badge: "RL",
      });
    }
    for (const c of complaints || []) {
      out.push({ key: `c${c.trackingId}${c.updatedAt}`, ts: Date.parse(c.updatedAt) / 1000, cat: "complaint", title: `${c.category} · ${c.status}`, text: `${c.title} (${c.trackingId})`, badge: "CV" });
    }
    for (const i of incidents || []) {
      out.push({ key: `i${i.incident_id || i.mission_id}`, ts: Date.parse(i.detected_at || i.created_at) / 1000 || 0, cat: "emergency", title: `${i.incident_type || "Incident"}${i.mission_id ? ` · ${i.status}` : ""}`, text: i.summary || i.description || i.location_label || i.scene?.name || "", badge: "ER" });
    }
    const q = query.trim().toLowerCase();
    return out
      .filter((x) => filter === "all" || CATEGORY_FILTER[x.cat] === filter)
      .filter((x) => !q || `${x.title} ${x.text}`.toLowerCase().includes(q))
      .sort((a, b) => b.ts - a.ts)
      .slice(0, 80);
  }, [events, decisions, complaints, incidents, filter, query]);

  const shown = (clusters || []).slice(0, 5);
  return (
    <aside className="activity" aria-label="City activity">
      <h2>City Activity</h2>
      <div className="muted">{today.toLocaleDateString([], { month: "long", day: "numeric", year: "numeric" })} · twin clock {simClock(simTime || 0).full}</div>
      <div className="days">
        {days.map((d, i) => (
          <div key={i} className={`day${i === 3 ? " on" : ""}`}>
            {d.getDate()}<small>{d.toLocaleDateString([], { weekday: "short" })}</small>
          </div>
        ))}
      </div>
      <h3>On-Duty Agents</h3>
      <div className="avatars">
        {shown.map((c, i) => (
          <span key={c.id} className="avatar" style={{ background: clusterColor(i) }} title={`${c.name} (${c.last?.decided_by === "llm" ? "Gemma" : "waiting"})`}>{initials(c.name)}</span>
        ))}
        {(clusters || []).length > 5 && <span className="avatar more">+{clusters.length - 5}</span>}
        <span className="avatar" style={{ background: "var(--ink)", marginLeft: 12 }} title="Double DQN signal controller">RL</span>
      </div>
      <div className="filters" role="group" aria-label="Filter activity">
        {FILTERS.map((f) => (
          <button key={f.id} className={`chip${filter === f.id ? " on" : ""}`} onClick={() => setFilter(f.id)}>{f.label}</button>
        ))}
      </div>
      <div className="timeline">
        {items.length === 0 && <div className="empty">Nothing yet for this filter.</div>}
        {items.map((x) => {
          const sim = x.sim !== undefined ? simClock(x.sim) : null;
          const ci = x.who !== undefined ? clusterIdx[x.who] : undefined;
          return (
            <div className="tl-row" key={x.key}>
              <div className="tl-time num">{sim ? sim.hm : wallTime(x.ts).slice(0, 5)}<small>{sim ? `${sim.ampm} · twin` : "live"}</small></div>
              <div className={`tl-card ${TONE[x.cat] || "grey"}`}>
                <div style={{ minWidth: 0 }}>
                  <div className="t">{x.title}</div>
                  <div className="s">{x.text}</div>
                </div>
                {ci !== undefined ? (
                  <span className="avatar" style={{ background: clusterColor(ci) }}>{initials(clusters[ci].name)}</span>
                ) : x.badge ? <span className="avatar" style={{ background: "rgba(0,0,0,.25)" }}>{x.badge}</span> : null}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
