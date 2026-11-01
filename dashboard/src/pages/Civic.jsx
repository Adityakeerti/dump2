import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertTriangle, Brain, BrainCircuit, Eye, FlaskConical, Gauge, Loader2, MessageCircleQuestion, Pause, Play, X } from "lucide-react";
import CivicMap3D, { DEPT_RGB } from "../components/CivicMap3D.jsx";
import { getJSON, postJSON } from "../lib/api.js";
import { fmt, initials } from "../lib/format.js";

// Civic simulator page: residents -> complaint portal -> Municipal / Police agents -> RL investigation policy.
const POLICY_LABEL = {
  rl: "RL policy (Double DQN)", tracer: "Deterministic tracer", complaint_count: "Complaint-chasing (status quo)", random: "Random",
};
const CAUSE_LABEL = {
  water_main_leak: "Water main leak", sewer_blockage: "Sewer blockage", missed_waste_route: "Missed waste route",
  streetlight_feeder_fault: "Streetlight feeder fault", crime_hotspot: "Crime hotspot",
};
const rgb = (d) => `rgb(${DEPT_RGB[d].join(",")})`;
const PERSONA_COLOR = { shopkeeper: "#2a78d6", "college student": "#1baf7a", "retired resident": "#c98500", "office commuter": "#6250d6", "daily-wage worker": "#d55181" };

function usePollRef(loader, ms) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const saved = useRef(loader);
  saved.current = loader;
  useEffect(() => {
    let alive = true, timer;
    const run = async () => {
      try { const d = await saved.current(); if (alive) { setData(d); setError(null); } } catch (e) { if (alive) setError(e.message); }
      if (alive) timer = setTimeout(run, ms);
    };
    run();
    return () => { alive = false; clearTimeout(timer); };
  }, [ms]);
  return { data, error };
}

function Tile({ on, icon: Icon, title, sub, onClick, children, open }) {
  return (
    <div style={{ position: "relative" }}>
      <button className={`tile${on ? " on" : ""}`} onClick={onClick} style={{ width: "100%" }} aria-expanded={open}>
        <span className="tile-icon"><Icon size={19} /></span>
        <span style={{ minWidth: 0 }}><div className="tile-title">{title}</div><div className="tile-sub">{sub}</div></span>
      </button>
      {open && children}
    </div>
  );
}

// LLM review of one root cause or hypothesis (Groq gpt-oss-120b -> 20b -> Gemma -> deterministic), like the twin's.
function LlmReview({ name }) {
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [trace, setTrace] = useState(false);
  useEffect(() => {
    let alive = true;
    setRes(null); setErr(null); setTrace(false);
    postJSON("/api/civic/root-cause", { asset_name: name }).then((r) => alive && setRes(r)).catch((e) => alive && setErr(e.message));
    return () => { alive = false; };
  }, [name]);
  if (err) return <div className="rc-verdict pending"><AlertTriangle size={14} /> LLM review failed: {err}</div>;
  if (!res) return <div className="rc-verdict pending"><Loader2 size={14} className="spin" /> LLM reasoning over the evidence (Groq gpt-oss-120b)…</div>;
  const a = res.analysis;
  return (
    <>
      <div className="rc-verdict">
        <div className="rc-verdict-top"><Brain size={14} /><span className="tag">LLM review</span><span className="tag">confidence {a.confidence}</span>
          <span className="tag">{a.agrees_with_system ? "agrees with the system" : "disagrees with the system"}</span></div>
        <p className="rc-headline">{a.headline}</p>
        <p><b>Root cause:</b> {a.root_cause}</p>
        {a.where_it_started && <p><b>Where / when it started:</b> {a.where_it_started}</p>}
        <p className="ink2">{a.system_comment}</p>
      </div>
      {a.reasoning_steps.length > 0 && <div className="rc-section"><div className="rc-section-head"><b>Reasoning, step by step</b></div><div className="rc-section-body">
        <ol className="rc-reasoning">{a.reasoning_steps.map((s, i) => <li key={i}>{s.claim}<div className="rc-evidence">{s.evidence}</div></li>)}</ol></div></div>}
      {a.policy_assessment && <div className="rc-section"><div className="rc-section-head"><b>How the departments' policy did</b></div><div className="rc-section-body">{a.policy_assessment}</div></div>}
      {(a.recommended_actions.length > 0 || a.alternatives_considered.length > 0) && <div className="rc-section"><div className="rc-section-head"><b>Actions and alternatives</b></div><div className="rc-section-body">
        <ul className="rc-list">{a.recommended_actions.map((x, i) => <li key={i}><b>{x.action}</b> · {x.owner}{x.expected_effect ? ` · ${x.expected_effect}` : ""}</li>)}</ul>
        {a.alternatives_considered.length > 0 && <><div className="muted" style={{ marginTop: 6 }}>Alternatives considered</div><ul className="rc-list">{a.alternatives_considered.map((x, i) => <li key={i}>{x}</li>)}</ul></>}
      </div></div>}
      {a.caveats.length > 0 && <div className="rc-section"><div className="rc-section-head"><b>Caveats</b></div><div className="rc-section-body"><ul className="rc-list">{a.caveats.map((x, i) => <li key={i}>{x}</li>)}</ul></div></div>}
      <div className="rc-model muted">
        {res.provider === "none" ? <><AlertTriangle size={12} /> No LLM reachable; showing the system's own record. {res.attempts?.map((x) => x.error).join(" · ")}</> : <>
          {res.model} via {res.provider}{res.latency_ms ? ` · ${(res.latency_ms / 1000).toFixed(1)} s` : ""}{res.cached ? " · cached" : ""} ·{" "}
          {res.ungrounded_numbers?.length ? <span className="err">⚠ numbers not in the evidence: {res.ungrounded_numbers.join(", ")}</span> : <span>✓ every number cited appears in the evidence</span>}
          {res.attempts?.length > 0 && <> · fell back after: {res.attempts.map((x) => x.model).join(", ")}</>}
          {res.reasoning_trace && <> · <button className="linkish" onClick={() => setTrace(!trace)}>{trace ? "hide" : "show"} model reasoning trace</button>
            {trace && <pre className="raw">{res.reasoning_trace}</pre>}</>}
        </>}
      </div>
    </>
  );
}

function Drawer({ item, last, onClose }) {
  if (!item) return null;
  if (item.kind === "truth") {
    return (
      <aside className="rc-drawer" aria-label="Previous episode">
        <div className="rc-head"><div><h2>Previous episode: was the diagnosis right?</h2><div className="muted">Seed {last?.seed} · ground truth is revealed only after the episode ends</div></div>
          <button className="round-btn" onClick={onClose} aria-label="Close"><X size={16} /></button></div>
        {!last ? <div className="empty">No episode has finished yet.</div> : <>
          <div className="rc-section"><div className="rc-section-head"><b>Hidden truth (planted causes)</b></div><div className="rc-section-body">
            {last.ground_truth.length === 0 && <div>No cause was planted (control episode): only random potholes and background complaints.</div>}
            {last.ground_truth.map((g, i) => (
              <div key={i} style={{ marginBottom: 6 }}><b>{CAUSE_LABEL[g.cause_type] || g.cause_type}</b> at {g.asset_name}<br />
                <span className="muted">started tick {g.onset_tick} · {g.identified_tick === null ? <span className="err">missed</span> : `confirmed tick ${g.identified_tick}`}{g.fixed_tick !== null ? ` · fixed tick ${g.fixed_tick}` : ""}</span></div>
            ))}
          </div></div>
          <div className="rc-section"><div className="rc-section-head"><b>What the departments reported</b></div><div className="rc-section-body">
            {last.diagnosis.root_causes.length === 0 && <div>No root cause confirmed.</div>}
            {last.diagnosis.root_causes.map((r, i) => {
              const hit = last.ground_truth.some((g) => g.asset_name === r.where.asset);
              return <div key={i} style={{ marginBottom: 6 }}><span className={`tag ${hit ? "exploit" : "shield"}`}>{hit ? "correct" : "not planted"}</span> {r.where.asset} · started ~{r.started?.estimated ?? "unclear"} · confirmed {r.confirmed.at}</div>;
            })}
          </div></div>
          <div className="rc-kv">
            <span>Complaints</span><b className="num">{last.metrics.complaints}</b>
            <span>Inspections / repairs</span><b className="num">{last.metrics.inspections} / {last.metrics.repairs}</b>
            <span>False repairs</span><b className="num">{last.metrics.false_repairs}</b>
            <span>Symptom fixes</span><b className="num">{last.metrics.symptom_actions}</b>
            <span>Team reward</span><b className="num">{last.metrics.reward}</b>
          </div>
        </>}
      </aside>
    );
  }
  const r = item;
  const hyp = r.status === "HYPOTHESIS";
  return (
    <aside className="rc-drawer" aria-label="Root cause">
      <div className="rc-head"><div><h2>{hyp ? "Hypothesis" : "Root cause"}: {hyp ? r.asset_name : r.where.asset}</h2>
        <div className="muted">{hyp ? `unconfirmed · score ${r.score} · coverage ${r.coverage} · lift ${r.lift}` : `${r.status} · ${r.responsible_department} · ward ${r.where.ward} · block ${r.where.block}`}</div></div>
        <button className="round-btn" onClick={onClose} aria-label="Close"><X size={16} /></button></div>
      <div className={`rc-verdict${hyp ? " pending" : ""}`}>
        {hyp ? <>Not confirmed (system). Next step: <b>{r.next_step}</b>. If true: {r.why_if_true}.</> : <>
          <div className="rc-verdict-top"><span className="sim-badge">SIMULATED</span><span className="tag">confirmed {r.confirmed.at} by {r.confirmed.by}</span>{r.fixed_at && <span className="tag">fixed {r.fixed_at}</span>}</div>
          <p className="rc-headline"><b>Why:</b> {r.why}</p>
          <p className="ink2">Method: {r.confirmed.method} · decided by the <b>{r.confirmed.policy}</b> policy</p>
        </>}
      </div>
      <LlmReview name={hyp ? r.asset_name : r.where.asset} />
      {!hyp && <>
        <div className="rc-divider">System record (deterministic, from the portal and the work log)</div>
        <div className="rc-kv">
          <span>Where</span><b>{r.where.asset} · {r.where.block} · ward {r.where.ward}</b>
          <span>Coordinates</span><span className="num ink2">{r.where.lat}, {r.where.lon}</span>
          <span>Started (estimate)</span><b>{r.started?.estimated ?? "no clear change point yet"}{r.started?.first_noticed_block ? ` · first noticed at ${r.started.first_noticed_block}` : ""}</b>
          <span>Affected</span><b className="num">{r.affected.complaints} complaints · {r.affected.blocks} blocks · wards {r.affected.wards.join(", ")}</b>
        </div>
        {r.started && <div className="muted" style={{ fontSize: 11 }}>{r.started.method}. {r.started.note}.</div>}
        <div className="rc-section"><div className="rc-section-head"><b>How it spread (symptom chain)</b></div><div className="rc-section-body">
          <ol className="rc-reasoning">{r.symptom_chain.map((e) => (
            <li key={e.category}><b>{e.label}</b>: {e.count} complaints, first {e.first_seen} at {e.first_block}
              <div className="rc-evidence">routed to {e.unit} ({e.routed_to})</div></li>))}</ol>
        </div></div>
        {r.cross_department.length > 0 && <div className="rc-section"><div className="rc-section-head"><b>Cross-department</b></div><div className="rc-section-body">
          <ul className="rc-list">{r.cross_department.map((x) => <li key={x}>{x}</li>)}</ul></div></div>}
        <div className="rc-divider">Evidence: {r.evidence_ids.join(", ")}</div>
      </>}
      <div className="rc-divider">A root cause is shown only after a field inspection or repair in the simulation found the fault. Ranked candidates without that are hypotheses.</div>
    </aside>
  );
}

export default function Civic({ theme, query }) {
  const tickRef = useRef(0);
  const health = usePollRef(() => getJSON("/api/civic/health"), 1000);
  const st = usePollRef(() => getJSON("/api/civic/state"), 1000);
  const diag = usePollRef(() => getJSON("/api/civic/diagnosis"), 2000);
  const mapQ = usePollRef(() => getJSON("/api/civic/map"), 60000);
  const last = usePollRef(() => getJSON("/api/civic/last_episode").catch(() => null), 5000);
  const fresh = usePollRef(() => getJSON(`/api/civic/complaints?since_tick=${Math.max(0, tickRef.current - 2)}&limit=400`), 1000);
  const [view, setView] = useState("city");
  const [menu, setMenu] = useState(null);
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("all");
  const [show, setShow] = useState({ water: true, sewer: true, waste: false, lights: true });
  const [legend, setLegend] = useState(false);
  const [explained, setExplained] = useState({});
  const explain = async (id) => {
    setExplained((e) => ({ ...e, [id]: { busy: true } }));
    try { const r = await postJSON("/api/civic/explain", { action_id: id }); setExplained((e) => ({ ...e, [id]: r })); }
    catch (err) { setExplained((e) => ({ ...e, [id]: { error: err.message } })); }
  };
  const h = health.data;
  tickRef.current = h?.tick ?? 0;

  // complaints and actions get a first-seen wall time so the map can animate them once
  const store = useRef({ seed: null, primed: false, complaints: new Map(), actions: new Map() });
  const [, bump] = useState(0);
  useEffect(() => {
    const s = store.current;
    if (h && s.seed !== h.episode_seed) { s.seed = h.episode_seed; s.complaints = new Map(); s.actions = new Map(); s.primed = false; }
    const t = performance.now() / 1000;
    let added = false;
    for (const c of fresh.data || []) if (!s.complaints.has(c.id)) { s.complaints.set(c.id, { ...c, _seen: s.primed ? t : -1e9 }); added = true; }
    for (const a of st.data?.actions || []) if (!s.actions.has(a.id)) { s.actions.set(a.id, { ...a, _seen: s.primed ? t : -1e9 }); added = true; }
    if (fresh.data) s.primed = true;
    if (s.complaints.size > 600) s.complaints = new Map([...s.complaints].slice(-400));
    if (added) bump((x) => x + 1);
  }, [fresh.data, st.data, h]);
  const complaints = [...store.current.complaints.values()];
  const actions = [...store.current.actions.values()];

  const act = async (body) => { setMenu(null); try { await postJSON("/api/civic/control", body); } catch (e) { alert(e.message); } };
  const reset = async (scenario) => { setMenu(null); setSelected(null); try { await postJSON("/api/civic/reset", { scenario }); } catch (e) { alert(e.message); } };

  const s = st.data;
  const d = diag.data;
  const m = s?.metrics || {};
  const roots = d?.root_causes || [];
  const lastTick = complaints.filter((c) => c.tick === (h?.tick ?? 0)).length;
  const llm = complaints.filter((c) => c.text_by === "llm").length;
  const progress = h ? h.tick / h.horizon : 0;
  const scenarioLabel = h?.scenario === null || h?.scenario === undefined ? "random causes (hidden)" : h.scenario.length ? `${h.scenario.map((x) => CAUSE_LABEL[x] || x).join(" + ")} (location hidden)` : "control: no planted cause";

  const feed = useMemo(() => {
    const q = (query || "").toLowerCase();
    const items = [
      ...complaints.slice(-80).map((c) => ({ kind: "complaint", tick: c.tick, key: c.id, c })),
      ...actions.filter((a) => a.action !== "wait").map((a) => ({ kind: a.department, tick: a.tick, key: a.id, a })),
    ].filter((x) => filter === "all" || (filter === "residents" ? x.kind === "complaint" : x.kind === filter))
      .filter((x) => !q || JSON.stringify(x.c || x.a).toLowerCase().includes(q));
    return items.sort((x, y) => y.tick - x.tick || (x.kind === "complaint") - (y.kind === "complaint")).slice(0, 90);
  }, [complaints, actions, filter, query]);

  return (
    <div className="dash">
      <div className="col">
        <div className="map-card" style={{ height: 600 }}>
          <div className="map-notch" role="tablist">
            {[["city", "3D City"], ["satellite", "Satellite"]].map(([id, label]) => (
              <button key={id} className={`notch-btn${view === id ? " on" : ""}`} onClick={() => setView(id)} role="tab" aria-selected={view === id}>{label}</button>
            ))}
          </div>
          <CivicMap3D map={mapQ.data} state={s} health={h} complaints={complaints} actions={actions} diagnosis={d}
            mode={view} theme={theme} show={show} selected={selected?.kind === "truth" ? null : selected} onSelect={setSelected}
            overlays={h && (<>
              <div className="map-overlay tl num">
                <span className="sim-badge">SIMULATED</span> <b>{h.clock}</b> · tick {h.tick}/{h.horizon}
                <div className="bar-track" style={{ width: 160, margin: "6px 0 4px", background: "rgba(255,255,255,.15)" }}>
                  <span className="bar-fill" style={{ left: 0, width: `${progress * 100}%`, background: "var(--peach)" }} />
                </div>
                departments: {POLICY_LABEL[h.policy]}{h.policy !== h.policy_requested ? " (no checkpoint)" : ""}<br />
                scenario: {scenarioLabel}<br />
                {h.residents} residents · Gemma {h.llm_ok === null ? "idle" : h.llm_ok ? "writing complaints" : "offline (templates)"}<br />
                <span style={{ opacity: 0.7 }}>schematic block grid on a real Dehradun basemap</span>
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 6 }}>
                  {[["water", "Water mains"], ["sewer", "Sewers"], ["waste", "Waste routes"], ["lights", "Streetlights"]].map(([k, l]) => (
                    <button key={k} className={`chip${show[k] ? " on" : ""}`} style={{ fontSize: 10 }} onClick={() => setShow({ ...show, [k]: !show[k] })}>{l}</button>
                  ))}
                </div>
              </div>
              {!legend ? <button className="map-overlay bl" style={{ display: "block", cursor: "pointer" }} onClick={() => setLegend(true)}>Legend ▴</button> : (
              <div className="map-overlay bl" onClick={() => setLegend(false)} style={{ cursor: "pointer" }} title="Click to hide">
                <div className="legend-row"><span style={{ width: 10, height: 10, background: rgb("municipal") }} /> Nagar Nigam HQ · municipal complaint / crew</div>
                <div className="legend-row"><span style={{ width: 10, height: 10, background: rgb("police") }} /> Police station · police complaint / crew</div>
                <div className="legend-row"><span className="legend-swatch" style={{ background: "#2896ff" }} /> water main</div>
                <div className="legend-row"><span className="legend-swatch" style={{ background: "#96683c" }} /> sewer</div>
                <div className="legend-row"><span style={{ width: 8, height: 8, borderRadius: 4, background: "#1c1a18", border: "1px solid #a09682" }} /> pothole</div>
                <div className="legend-row"><span style={{ width: 8, height: 8, background: "#ffd65c" }} /> lamp (grey: residents report dark)</div>
                <div className="legend-row"><span style={{ width: 10, height: 10, borderRadius: 5, background: "#d62020", border: "2px solid #fff" }} /> confirmed root cause (green: fixed)</div>
                <div className="legend-row"><span style={{ width: 10, height: 10, borderRadius: 5, background: "#f09628", border: "2px solid #fff" }} /> hypothesis (unconfirmed)</div>
                <div className="legend-row"><span className="legend-swatch" style={{ background: "linear-gradient(90deg, rgba(208,59,59,.15), rgba(208,59,59,.7))", height: 8 }} /> block complaint heat</div>
                <div className="legend-row"><span className="legend-swatch" style={{ border: "1.5px solid #d62020", height: 8, background: "none" }} /> affected zone</div>
              </div>)}
            </>)}
          />
        </div>

        <div className="kpis">
          <div className="kpi"><div className="kpi-label">Complaints this episode</div><div className="kpi-value num">{m.complaints ?? "–"}</div>
            <div className="kpi-sub num">{lastTick} in the last tick · {llm} written by Gemma</div></div>
          <div className="kpi"><div className="kpi-label">Open department queues</div><div className="kpi-value num">{s ? s.queues.municipal + s.queues.police : "–"}</div>
            <div className="kpi-sub num"><span style={{ color: rgb("municipal") }}>municipal {s?.queues.municipal ?? "–"}</span> · <span style={{ color: rgb("police") }}>police {s?.queues.police ?? "–"}</span></div></div>
          <div className="kpi"><div className="kpi-label">Root causes confirmed</div><div className="kpi-value num">{roots.length}<span className="muted" style={{ fontSize: 13 }}> · {roots.filter((r) => r.status === "FIXED").length} fixed</span></div>
            <div className="kpi-sub">{(d?.hypotheses || []).length} open hypotheses</div></div>
          <div className="kpi"><div className="kpi-label">Crew work</div><div className="kpi-value num">{m.inspections ?? 0}<span className="muted" style={{ fontSize: 13 }}> inspections · {m.repairs ?? 0} repairs</span></div>
            <div className="kpi-sub num">{m.false_repairs ?? 0} false repairs · {m.symptom_actions ?? 0} symptom fixes · reward {fmt(m.reward, 1)}</div></div>
        </div>

        {h && (
          <div className="tiles">
            <Tile on={h.policy === "rl"} icon={BrainCircuit} title="Department policy" sub={`${POLICY_LABEL[h.policy]} decides inspections and repairs`} onClick={() => setMenu(menu === "policy" ? null : "policy")} open={menu === "policy"}>
              <div className="tile-menu">{Object.entries(POLICY_LABEL).map(([k, l]) => <button key={k} className={k === h.policy_requested ? "on" : ""} onClick={() => act({ policy: k })}>{l}</button>)}</div>
            </Tile>
            <Tile on={!!h.scenario?.length} icon={FlaskConical} title="Plant a problem" sub={`${scenarioLabel} · new episode`} onClick={() => setMenu(menu === "scen" ? null : "scen")} open={menu === "scen"}>
              <div className="tile-menu">
                <button onClick={() => reset(null)}>Random 1–2 hidden causes</button>
                {(h.cause_types || []).map((c) => <button key={c} onClick={() => reset([c])}>{CAUSE_LABEL[c] || c}</button>)}
                <button onClick={() => reset(["streetlight_feeder_fault", "water_main_leak"])}>Feeder fault + water leak</button>
                <button onClick={() => reset([])}>Control: no cause (noise only)</button>
              </div>
            </Tile>
            <Tile on={h.running} icon={h.running ? Activity : Pause} title="Simulation" sub={`${h.running ? "running" : "paused"} · 1 tick (${h.tick_hours} h) every ${fmt(h.tick_interval_sec, 1)} s`} onClick={() => setMenu(menu === "sim" ? null : "sim")} open={menu === "sim"}>
              <div className="tile-menu">
                <button onClick={() => act({ running: !h.running })}>{h.running ? <><Pause size={12} /> Pause</> : <><Play size={12} /> Play</>}</button>
                <button onClick={() => act({ running: false, step: 1 })}><Gauge size={12} /> Step one tick</button>
                {[1.5, 3, 6].map((x) => <button key={x} className={x === h.tick_interval_sec ? "on" : ""} onClick={() => act({ tick_interval_sec: x })}>1 tick every {x} s</button>)}
              </div>
            </Tile>
            <Tile on={selected?.kind === "truth"} icon={Eye} title="Reveal the truth" sub={last.data ? `previous episode: ${last.data.diagnosis.root_causes.length} reported vs ${last.data.ground_truth.length} planted` : "available after the first episode ends"} onClick={() => setSelected({ kind: "truth" })} />
          </div>
        )}
      </div>

      <aside className="activity" aria-label="City activity">
        <h2>City activity</h2>
        <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>Residents report to the portal; departments act each tick.</div>
        {roots.length > 0 && (
          <div style={{ display: "grid", gap: 6, margin: "12px 0 4px" }}>
            {roots.map((r) => (
              <button key={r.where.asset} className="tl-card green" style={{ textAlign: "left", background: r.status === "FIXED" ? "var(--green)" : "#b01818" }} onClick={() => setSelected(r)}>
                <span><div className="t">{r.status === "FIXED" ? "Root cause fixed" : "Root cause confirmed"}: {r.where.asset}</div>
                  <div className="s">started ~{r.started?.estimated ?? "?"} · {r.affected.complaints} complaints · {r.cross_department.length ? "crossed departments · " : ""}click for trace</div></span>
              </button>
            ))}
          </div>
        )}
        {(d?.hypotheses || []).slice(0, 2).map((hy) => (
          <button key={hy.asset_name} className="tl-card grey" style={{ textAlign: "left", margin: "4px 0" }} onClick={() => setSelected(hy)}>
            <span><div className="t">Hypothesis: {hy.asset_name}</div><div className="s">score {hy.score} · next: {hy.next_step}</div></span>
          </button>
        ))}
        <div className="filters" style={{ marginTop: 10 }}>
          {[["all", "All"], ["residents", "Residents"], ["municipal", "Municipal"], ["police", "Police"]].map(([k, l]) => (
            <button key={k} className={`chip${filter === k ? " on" : ""}`} onClick={() => setFilter(k)}>{l}</button>
          ))}
        </div>
        <div className="timeline">
          {feed.length === 0 && <div className="empty">{health.error ? `Civic simulator offline: ${health.error}` : "Waiting for the first tick…"}</div>}
          {feed.map((x) => x.kind === "complaint" ? (
            <div className="tl-row" key={x.key}>
              <div className="tl-time">{x.c.clock.split(" ")[2]}<small>{x.c.clock.split(" ").slice(0, 2).join(" ")}</small></div>
              <div className="tl-card grey">
                <span style={{ minWidth: 0 }}><div className="t">{x.c.label} · {x.c.block}</div>
                  <div className="s">“{x.c.text}”</div>
                  <div className="s" style={{ color: rgb(x.c.department) }}>→ {x.c.unit}{x.c.text_by === "llm" ? " · written by citizen agent" : ""}</div></span>
                <span className="avatar" title={`${x.c.citizen.id} · ${x.c.citizen.persona}`} style={{ background: PERSONA_COLOR[x.c.citizen.persona] || "#888" }}>{initials(x.c.citizen.persona)}</span>
              </div>
            </div>
          ) : (
            <div className="tl-row" key={x.key}>
              <div className="tl-time">{x.a.clock.split(" ")[2]}<small>{x.a.clock.split(" ").slice(0, 2).join(" ")}</small></div>
              <div className={`tl-card ${x.kind === "police" ? "peach" : "green"}`}>
                <span style={{ minWidth: 0 }}><div className="t">{x.kind === "police" ? "Police" : "Municipal"} {x.a.action}: {x.a.asset_name}</div>
                  <div className="s">{x.a.found_fault ? (["road", "traffic"].includes(x.a.layer) ? "symptoms treated" : "FAULT FOUND") : x.a.action === "inspect" ? "nothing found" : ["road", "traffic"].includes(x.a.layer) ? "symptom fix" : "nothing wrong: wasted repair"}{x.a.bonus ? ` · ${x.a.bonus}` : ""}</div>
                  {!explained[x.a.id] && <button className="s" style={{ textDecoration: "underline", marginTop: 3, display: "inline-flex", gap: 4, alignItems: "center" }} onClick={() => explain(x.a.id)}><MessageCircleQuestion size={11} /> Why this action? (Gemma)</button>}
                  {explained[x.a.id]?.busy && <div className="s"><Loader2 size={11} className="spin" /> asking Gemma…</div>}
                  {explained[x.a.id]?.error && <div className="s">explanation unavailable: {explained[x.a.id].error}</div>}
                  {explained[x.a.id]?.explanation && <div className="s" style={{ marginTop: 4, background: "rgba(255,255,255,.14)", borderRadius: 8, padding: "5px 7px" }}>
                    {explained[x.a.id].explanation}
                    <div style={{ opacity: 0.8, marginTop: 2 }}>{explained[x.a.id].grounded ? `✓ ${explained[x.a.id].model} · numbers checked against the decision record` : explained[x.a.id].note}
                      {explained[x.a.id].record?.chosen?.q !== undefined && ` · Q ${explained[x.a.id].record.chosen.q} vs next ${explained[x.a.id].record.alternatives[0]?.q ?? "–"}`}</div>
                  </div>}</span>
              </div>
            </div>
          ))}
        </div>
      </aside>
      <Drawer item={selected} last={last.data} onClose={() => setSelected(null)} />
    </div>
  );
}
