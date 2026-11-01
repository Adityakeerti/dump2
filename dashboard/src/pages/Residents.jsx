import { useState } from "react";
import { Pause, Play, RefreshCw } from "lucide-react";
import { cityControl } from "../lib/api.js";
import { clusterColor, fmt, initials, wallTime } from "../lib/format.js";

const NODE_ORDER = ["observe", "decide", "validate", "fallback", "dispatch"];

function TraceRow({ t, color }) {
  const [open, setOpen] = useState(false);
  const decide = t.steps.find((s) => s.node === "decide");
  const observe = t.steps.find((s) => s.node === "observe");
  return (
    <div className="decision">
      <div className="decision-top">
        <span className="avatar" style={{ background: color, width: 24, height: 24, fontSize: 9 }}>{initials(t.cluster)}</span>
        <b>{t.cluster}</b>
        <span className="num">{t.clock} · ep {t.episode + 1}</span>
        <span className={`tag ${t.decided_by === "llm" ? "llm" : "fallback"}`}>{t.decided_by === "llm" ? "Gemma decided" : "rule fallback"}</span>
        <span className="muted num" style={{ marginLeft: "auto" }}>{fmt(t.total_ms, 0)} ms · {wallTime(t.ts)}</span>
      </div>
      <div className="trace-steps">
        {NODE_ORDER.map((n) => {
          const s = t.steps.find((x) => x.node === n);
          if (!s) return n === "fallback" ? null : <span key={n} className="trace-node muted">{n}</span>;
          const bad = s.error || s.ok === false;
          return <span key={n} className={`trace-node ${bad ? "bad" : "ok"}`} title={s.error || ""}>{n} {fmt(s.ms, 0)}ms</span>;
        }).filter(Boolean).reduce((acc, el, i) => (i ? [...acc, <span key={`a${i}`} className="muted">→</span>, el] : [el]), [])}
      </div>
      <div>
        <b>{t.plan.intent}</b> · leave <b>{t.plan.departure?.replace("_", " ")}</b> · share <b>{t.plan.share}</b> → {t.car_clusters} car clusters, {fmt(t.vehicles, 0)} vehicles
        <div className="ink2" style={{ fontStyle: "italic" }}>“{t.plan.reason}”</div>
      </div>
      <button className="chip" style={{ justifySelf: "start" }} onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"} prompt & raw output</button>
      {open && (
        <>
          <div className="muted" style={{ fontSize: 11 }}>Observation sent to the model:</div>
          <pre className="raw">{observe?.summary}</pre>
          <div className="muted" style={{ fontSize: 11 }}>Model output ({decide?.model}):</div>
          <pre className="raw">{decide?.raw || decide?.error || "–"}</pre>
        </>
      )}
    </div>
  );
}

export default function Residents({ city }) {
  const health = city?.health;
  const clusters = city?.clusters?.clusters || [];
  const traces = city?.traces?.traces || [];
  const idx = Object.fromEntries(clusters.map((c, i) => [c.id, i]));

  return (
    <div className="col">
      <div className="page-head">
        <div>
          <h1>Residents</h1>
          <p>
            Each people cluster is a LangGraph agent (observe → decide → validate → fallback → dispatch) backed by local Gemma-4-E2B on llama-server.
            Agents read live corridor conditions and their own past delays, then pick a categorical plan. Vehicle counts and departure times are computed
            from config tables, so the model never invents numbers; invalid or missing LLM output falls back to a visible rule.
          </p>
        </div>
        {health && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn ghost" onClick={() => cityControl({ plan_now: true })}><RefreshCw size={13} /> Plan now</button>
            <button className={`btn${health.enabled ? "" : " peach"}`} onClick={() => cityControl({ enabled: !health.enabled })}>
              {health.enabled ? <><Pause size={13} /> Pause agents</> : <><Play size={13} /> Resume agents</>}
            </button>
          </div>
        )}
      </div>

      {!health && <div className="panel err">Population service unreachable (expected at /api/city → port 8004). {city?.error}</div>}
      {health && (
        <div className="kpis">
          <div className="kpi"><div className="kpi-label">LLM server</div><div className="kpi-value"><span className={`dot ${health.llm_server ? "up" : "down"}`} style={{ display: "inline-block", marginRight: 6 }} />{health.llm_server ? "online" : "offline"}</div><div className="kpi-sub">{health.llm_model} via llama-server</div></div>
          <div className="kpi"><div className="kpi-label">Planning rounds</div><div className="kpi-value num">{health.rounds}</div><div className="kpi-sub">{health.round_running ? "round in progress…" : `every ${health.planning_interval_sim_sec / 60} simulated min`}</div></div>
          <div className="kpi"><div className="kpi-label">Decisions by Gemma</div><div className="kpi-value num">{clusters.reduce((a, c) => a + c.stats.llm, 0)}</div><div className="kpi-sub num">{clusters.reduce((a, c) => a + c.stats.fallback, 0)} rule fallbacks</div></div>
          <div className="kpi"><div className="kpi-label">Vehicles generated</div><div className="kpi-value num">{fmt(clusters.reduce((a, c) => a + c.stats.vehicles, 0), 0)}</div><div className="kpi-sub num">{clusters.reduce((a, c) => a + c.stats.trips, 0)} car clusters</div></div>
        </div>
      )}

      <div className="grid-3">
        {clusters.map((c, i) => (
          <div className="panel" key={c.id}>
            <div className="panel-head">
              <span className="avatar" style={{ background: clusterColor(i) }}>{initials(c.name)}</span>
              <h2 style={{ fontSize: 14 }}>{c.name}</h2>
              {c.last && <span className={`tag ${c.last.decided_by === "llm" ? "llm" : "fallback"}`}>{c.last.decided_by === "llm" ? "Gemma" : "fallback"}</span>}
            </div>
            <div className="muted" style={{ fontSize: 11.5 }}>{c.population} people · {c.persona}</div>
            {c.last ? (
              <div style={{ marginTop: 8 }}>
                <div><b>{c.last.clock}</b>: {c.last.plan.intent}, leave {c.last.plan.departure?.replace("_", " ")}, share {c.last.plan.share}</div>
                <div className="ink2" style={{ fontStyle: "italic", fontSize: 12 }}>“{c.last.plan.reason}”</div>
                <div className="muted num" style={{ fontSize: 11 }}>saw: speed {c.last.observation.mean_speed_pct}% · jammed {c.last.observation.jammed_links.length} · backlog {c.last.observation.entry_backlog_veh} veh</div>
              </div>
            ) : <div className="empty">Waiting for the first planning round.</div>}
            {c.memory.length > 0 && (
              <table style={{ marginTop: 8 }}>
                <thead><tr><th>Memory</th><th>Plan</th><th className="r">Realised delay</th></tr></thead>
                <tbody>
                  {[...c.memory].reverse().map((m) => (
                    <tr key={m.plan_id}><td className="num">ep {(m.episode ?? 0) + 1} · {m.clock}</td><td>{m.intent}/{m.departure}/{m.share}</td><td className="r num">{m.mean_delay_sec !== undefined ? `${fmt(m.mean_delay_sec, 0)}s` : "pending"}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
      </div>

      <div className="panel">
        <div className="panel-head"><h2>LangGraph traces</h2><span className="muted">newest first · {traces.length} kept</span></div>
        <div style={{ display: "grid", gap: 8 }}>
          {traces.length === 0 && <div className="empty">No agent runs yet.</div>}
          {[...traces].reverse().slice(0, 40).map((t) => <TraceRow key={t.id} t={t} color={clusterColor(idx[t.cluster_id] ?? 0)} />)}
        </div>
      </div>
    </div>
  );
}
