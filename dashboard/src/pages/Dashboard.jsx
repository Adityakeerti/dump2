import { useEffect, useRef, useState } from "react";
import { Activity, BrainCircuit, Gauge, Pause, Play, SearchCheck, TriangleAlert } from "lucide-react";
import CityMap3D from "../components/CityMap3D.jsx";
import Heatmap from "../components/Heatmap.jsx";
import ActivityPanel from "../components/ActivityPanel.jsx";
import RootCausePanel from "../components/RootCausePanel.jsx";
import { reasonRootCause, traceRootCause, twinControl } from "../lib/api.js";
import { fmt, POLICY_LABEL, simClock } from "../lib/format.js";

function Tile({ on, icon: Icon, title, sub, onClick, children, open }) {
  return (
    <div style={{ position: "relative" }}>
      <button className={`tile${on ? " on" : ""}`} onClick={onClick} style={{ width: "100%" }} aria-expanded={open}>
        <span className="tile-icon"><Icon size={19} /></span>
        <span style={{ minWidth: 0 }}>
          <div className="tile-title">{title}</div>
          <div className="tile-sub">{sub}</div>
        </span>
      </button>
      {open && children}
    </div>
  );
}

export default function Dashboard({ twin, city, complaints, incidents, query, theme }) {
  const { topology, state, events, decisions, history } = twin;
  const [view, setView] = useState(() => (["city", "satellite", "heat"].includes(new URLSearchParams(location.search).get("view")) ? new URLSearchParams(location.search).get("view") : "city"));
  const [menu, setMenu] = useState(null);
  const [rc, setRc] = useState(null);
  const [busy, setBusy] = useState(null);
  const clusters = city?.clusters?.clusters || [];
  const cityHealth = city?.health;

  const act = async (body) => {
    setMenu(null);
    try { await twinControl(body); } catch (e) { alert(e.message); }
  };

  // Root cause of a live congestion point: deterministic trace in the twin, then LLM reasoning over it.
  const trace = async (point) => {
    setMenu(null);
    const cell = point.head_cell;
    setRc({ status: "tracing", point, cell });
    try {
      const diagnosis = await traceRootCause(cell);
      if (!diagnosis.found) return setRc({ status: "done", point, cell, diagnosis });
      setRc({ status: "reasoning", point, cell, diagnosis });
      const res = await reasonRootCause(cell, diagnosis);
      setRc({ status: "done", point, cell, diagnosis, llm: res.llm });
    } catch (e) {
      setRc((r) => ({ ...r, status: "error", error: e.message }));
    }
  };
  // ?trace=1 opens a trace of the worst congestion point as soon as one exists (demo / deep link).
  const autoTraced = useRef(false);
  useEffect(() => {
    if (autoTraced.current || !new URLSearchParams(location.search).get("trace")) return;
    const w = [...(state?.congestion_points || [])].filter((p) => state.sim_time - p.since_sec >= (topology?.diagnosis_min_jam_age_sec ?? 0)).sort((x, y) => x.min_speed_ratio - y.min_speed_ratio)[0];
    if (w) { autoTraced.current = true; trace(w); }
  });
  const minAge = topology?.diagnosis_min_jam_age_sec ?? 0;
  const maturePoints = (state?.congestion_points || []).filter((p) => state.sim_time - p.since_sec >= minAge);
  const worstPoint = () => [...maturePoints].sort((x, y) => x.min_speed_ratio - y.min_speed_ratio)[0]
    || [...(state?.congestion_points || [])].sort((x, y) => x.min_speed_ratio - y.min_speed_ratio)[0];

  const k = state?.kpis || {};
  const active = k[state?.policy] || {};
  const fixed = k["fixed-time"] || {};
  const jammed = (state?.links || []).filter((l) => l.jammed);
  const delta = active.mean_system_vehicles && fixed.mean_system_vehicles ? (1 - active.mean_system_vehicles / fixed.mean_system_vehicles) * 100 : null;
  const sc = topology?.scenarios?.find((s) => s.name === state?.scenario);
  const clock = state ? simClock(state.sim_time) : null;
  const progress = state ? state.sim_time / state.episode_duration_sec : 0;

  return (
    <div className="dash">
      <div className="col">
        <div className="map-card">
          <div className="map-notch" role="tablist">
            {[["city", "3D City"], ["satellite", "Satellite"], ["heat", "Time-space"]].map(([id, label]) => (
              <button key={id} className={`notch-btn${view === id ? " on" : ""}`} onClick={() => setView(id)} role="tab" aria-selected={view === id}>{label}</button>
            ))}
          </div>
          {view === "heat" ? (
            <div style={{ background: "var(--panel)", height: "100%", padding: "64px 18px 14px" }}>
              <Heatmap history={history} topology={topology} height={300} />
            </div>
          ) : (
            <CityMap3D
              topology={topology} state={state} clusters={clusters} traces={city?.traces?.traces || []}
              decisions={decisions} mode={view} theme={theme} onTrace={trace} diagnosis={rc?.diagnosis}
              overlays={state && (
                <>
                  <div className="map-overlay tl num">
                    <span className="sim-badge">SIMULATED</span> <b>{clock.full}</b> · episode {state.episode + 1}
                    <div className="bar-track" style={{ width: 150, margin: "6px 0 4px", background: "rgba(255,255,255,.15)" }}>
                      <span className="bar-fill" style={{ left: 0, width: `${progress * 100}%`, background: "var(--peach)" }} />
                    </div>
                    signals: {POLICY_LABEL[state.policy]}<br />
                    scenario: {state.scenario.replaceAll("_", " ")}
                  </div>
                  <div className="map-overlay bl">
                    {[["#0ca30c", "free flow ≥90%"], ["#fab219", "slowing"], ["#ec835a", "congested"], ["#d03b3b", "jam < 30%"]].map(([c, l]) => (
                      <div className="legend-row" key={l}><span className="legend-swatch" style={{ background: c }} />{l}</div>
                    ))}
                    <div className="legend-row"><span className="legend-swatch" style={{ background: "#2a78d6", height: 6 }} /> agent car cluster + trail</div>
                    <div className="legend-row"><span className="legend-swatch" style={{ background: "#eceef0", height: 6 }} /> background traffic</div>
                    <div className="legend-row"><span style={{ width: 8, height: 8, borderRadius: 4, background: "#eb6834", border: "1.5px solid #fff" }} /> people walking to cars</div>
                    <div className="legend-row"><span className="legend-swatch" style={{ background: "linear-gradient(90deg,#16c85a 50%,#eb3737 50%)", height: 4 }} /> signal stop line</div>
                    <div className="legend-row"><span style={{ width: 10, height: 10, borderRadius: 5, background: "#de1c1c", border: "2px solid #fff", boxShadow: "0 0 0 3px rgba(232,36,36,.35)" }} /> congestion point (red: traceable · orange: maturing)</div>
                  </div>
                </>
              )}
            />
          )}
        </div>

        <div className="kpis">
          <div className="kpi">
            <div className="kpi-label">Vehicles in system</div>
            <div className="kpi-value num">{fmt(active.system_vehicles, 0)}</div>
            <div className="kpi-sub num">episode mean {fmt(active.mean_system_vehicles)} {delta !== null && state.policy !== "fixed-time" && <>· {delta >= 0 ? "▼" : "▲"} {fmt(Math.abs(delta), 0)}% vs fixed-time</>}</div>
          </div>
          <div className="kpi">
            <div className="kpi-label">Congested links</div>
            <div className="kpi-value num">{jammed.length}<span className="muted" style={{ fontSize: 13 }}> / {state?.links?.length ?? "–"}</span></div>
            <div className="kpi-sub">{jammed.map((l) => l.name.replace("link ", "")).join(", ") || "none confirmed"}</div>
          </div>
          <div className="kpi">
            <div className="kpi-label">Car clusters</div>
            <div className="kpi-value num">{state?.platoons?.length ?? 0}<span className="muted" style={{ fontSize: 13 }}> active</span></div>
            <div className="kpi-sub num">{active.platoons_done ?? 0} finished · mean delay {fmt(active.mean_delay_sec, 0)}s</div>
          </div>
          <div className="kpi">
            <div className="kpi-label">RL exploration</div>
            <div className="kpi-value num">ε {fmt(state?.learning?.epsilon, 2)}</div>
            <div className="kpi-sub num">{fmt((state?.learning?.recent_explore_rate || 0) * 100, 0)}% random actions · {state?.learning?.updates ?? 0} updates</div>
          </div>
        </div>

        {state && topology && (
          <div className="tiles">
            <Tile on={state.policy === topology.learning_policy} icon={BrainCircuit} title="Signal policy" sub={`${POLICY_LABEL[state.policy]} drives the map`} onClick={() => setMenu(menu === "policy" ? null : "policy")} open={menu === "policy"}>
              <div className="tile-menu">
                {topology.policies.map((p) => <button key={p} className={p === state.policy ? "on" : ""} onClick={() => act({ policy: p })}>{POLICY_LABEL[p]} — mean {fmt(k[p]?.mean_system_vehicles)} veh</button>)}
              </div>
            </Tile>
            <Tile on={(state.disruptions || []).length > 0} icon={TriangleAlert} title="Scenario" sub={`${state.scenario.replaceAll("_", " ")}${state.disruptions.length ? " · disruption active" : ""}`} onClick={() => setMenu(menu === "scenario" ? null : "scenario")} open={menu === "scenario"}>
              <div className="tile-menu">
                {topology.scenarios.map((s) => <button key={s.name} className={s.name === state.scenario ? "on" : ""} onClick={() => act({ scenario: s.name })} title={s.description}>{s.name.replaceAll("_", " ")} <span className="muted">· {s.description}</span></button>)}
              </div>
            </Tile>
            <Tile on={!!rc} icon={SearchCheck} title="Diagnose root cause"
              sub={maturePoints.length ? `${maturePoints.length} traceable congestion point(s) · trace the worst, or click a red ripple`
                : (state.congestion_points || []).length ? `${state.congestion_points.length} jam(s) maturing (traceable after ${minAge} s)` : "no confirmed congestion right now"}
              onClick={() => { const w = worstPoint(); if (w) trace(w); }} />
            <Tile on={state.status === "running"} icon={state.status === "running" ? Activity : Pause} title="Simulation" sub={`${state.status} · ${fmt(state.steps_per_tick / topology.tick_interval_sec, 0)}× real time`} onClick={() => setMenu(menu === "sim" ? null : "sim")} open={menu === "sim"}>
              <div className="tile-menu">
                <button onClick={() => act({ action: state.status === "running" ? "pause" : "play" })}>{state.status === "running" ? <><Pause size={12} /> Pause</> : <><Play size={12} /> Play</>}</button>
                <button onClick={() => act({ action: "step" })}><Gauge size={12} /> Step {state.steps_per_tick}s</button>
                {topology.speed_options.map((s) => <button key={s} className={s === state.steps_per_tick ? "on" : ""} onClick={() => act({ steps_per_tick: s })}>Speed {fmt(s / topology.tick_interval_sec, 0)}× real time</button>)}
                <button onClick={() => act({ action: "reset" })}>Restart episode</button>
              </div>
            </Tile>
          </div>
        )}
      </div>

      <ActivityPanel events={events} decisions={decisions} clusters={clusters} complaints={complaints} incidents={incidents} query={query} simTime={state?.sim_time} />
      {rc && <RootCausePanel rc={rc} onClose={() => setRc(null)} />}
    </div>
  );
}
