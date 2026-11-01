import { fmt, wallTime } from "../lib/format.js";

const Down = ({ what, error, hint }) => (
  <div className="panel"><b>{what} is not reachable.</b> <span className="muted">{error}</span><p className="muted">{hint}</p></div>
);

export function TownHall({ feed, error }) {
  if (!feed) return <Down what="Complaint module" error={error} hint="Start it with ./run_backends.sh start (port 8001)." />;
  const s = feed.summary;
  return (
    <div className="col">
      <div className="page-head"><div><h1>TownHall</h1><p>Citizen complaints and their SLA escalation ladder, from the complaint module.</p></div></div>
      <div className="kpis">
        <div className="kpi"><div className="kpi-label">Total</div><div className="kpi-value num">{s.total_complaints}</div></div>
        <div className="kpi"><div className="kpi-label">Active</div><div className="kpi-value num">{s.active_unresolved}</div></div>
        <div className="kpi"><div className="kpi-label">Resolved</div><div className="kpi-value num">{s.resolved}</div></div>
        <div className="kpi"><div className="kpi-label">Feed time</div><div className="kpi-value" style={{ fontSize: 14 }}>{new Date(feed.feed_timestamp).toLocaleTimeString()}</div></div>
      </div>
      <div className="panel scroll">
        <table>
          <thead><tr><th>Tracking</th><th>Title</th><th>Category</th><th>Status</th><th className="r">Warnings</th><th className="r">SLA left</th><th>Worker</th><th>Authority</th><th>Updated</th></tr></thead>
          <tbody>
            {feed.complaints.map((c) => (
              <tr key={c.trackingId}>
                <td className="num">{c.trackingId}</td><td>{c.title}</td><td>{c.category}</td><td><span className="tag rule">{c.status}</span></td>
                <td className="r num">{c.warningsCount}</td><td className="r num">{c.slaRemainingSeconds !== null ? `${fmt(c.slaRemainingSeconds / 60, 0)} min` : "–"}</td>
                <td>{c.assignedWorker?.name || "–"}</td><td>{c.currentAuthority?.name || c.currentAuthority?.title || "–"}</td>
                <td className="num">{new Date(c.updatedAt).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {feed.complaints.length === 0 && <div className="empty">No complaints filed.</div>}
      </div>
    </div>
  );
}

export function Tickets({ missions, incidents, error }) {
  if (!missions && !incidents) return <Down what="Emergency routing" error={error} hint="Start it with ./run_backends.sh start (port 8002)." />;
  return (
    <div className="col">
      <div className="page-head"><div><h1>Tickets</h1><p>Emergency missions (dispatch, hospital, green-wave route) and CCTV-detected incidents from the emergency routing service. {missions?.network && <>Network: {missions.network}.</>}</p></div></div>
      <div className="panel scroll">
        <div className="panel-head"><h2>Missions</h2></div>
        <table>
          <thead><tr><th>Mission</th><th>Status</th><th>Type</th><th>Severity</th><th>Unit</th><th>Scene</th><th>Hospital</th><th>Green wave</th><th>Created</th></tr></thead>
          <tbody>
            {(missions?.missions || []).map((m) => (
              <tr key={m.mission_id}>
                <td className="num">{m.mission_id}</td><td><span className="tag rule">{m.status}</span></td><td>{m.incident_type}</td><td>{m.severity}</td>
                <td>{m.unit_id || m.unit_type}</td><td>{m.scene?.name}</td><td>{m.hospital?.name || "–"}</td><td>{m.green_wave_active ? "yes" : "no"}</td>
                <td className="num">{new Date(m.created_at).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!(missions?.missions || []).length && <div className="empty">No missions dispatched.</div>}
      </div>
      <div className="panel scroll">
        <div className="panel-head"><h2>Incidents</h2></div>
        <table>
          <thead><tr><th>Incident</th><th>Type</th><th className="r">Confidence</th><th>Camera</th><th>Location</th><th>Detected</th></tr></thead>
          <tbody>
            {(incidents?.incidents || []).map((i) => (
              <tr key={i.incident_id}><td className="num">{i.incident_id}</td><td>{i.incident_type}</td><td className="r num">{fmt(i.confidence, 2)}</td><td>{i.camera_id}</td><td>{i.location_label || "–"}</td><td className="num">{new Date(i.detected_at).toLocaleTimeString()}</td></tr>
            ))}
          </tbody>
        </table>
        {!(incidents?.incidents || []).length && <div className="empty">No incidents recorded.</div>}
      </div>
    </div>
  );
}

export function Messages({ events, error }) {
  if (!events) return <Down what="Voice agent event log" error={error} hint="Needs the agent service on port 8000 with DEMO_MODE=1 (dev admin token)." />;
  return (
    <div className="col">
      <div className="page-head"><div><h1>Messages</h1><p>Citizen conversations with the multilingual voice agent: guardrail verdicts, planner steps and the backend each tool call reached.</p></div></div>
      <div className="panel scroll">
        <table>
          <thead><tr><th>#</th><th>Time</th><th>Kind</th><th>Source</th><th>Details</th></tr></thead>
          <tbody>
            {[...events].reverse().map((e) => {
              const { id, ts, kind, source, ...rest } = e;
              const text = rest.text || rest.message || rest.transcript || rest.reply || "";
              const tools = (rest.tools || rest.tool_calls || []).map((t) => t.name || t.tool).filter(Boolean);
              return (
                <tr key={id}>
                  <td className="num">{id}</td><td className="num">{wallTime(Date.parse(ts) / 1000)}</td><td><span className="tag rule">{kind}</span></td><td>{source || "–"}</td>
                  <td style={{ maxWidth: 520 }}>{String(text).slice(0, 220)}{tools.length > 0 && <div className="muted">tools: {tools.join(", ")}</div>}{rest.scope && <div className="muted">scope: {String(rest.scope)}</div>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {events.length === 0 && <div className="empty">No agent activity yet.</div>}
      </div>
    </div>
  );
}
