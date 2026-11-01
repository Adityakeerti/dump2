import { useState } from "react";
import { AlertTriangle, Brain, CheckCircle2, ChevronDown, ChevronRight, Loader2, X } from "lucide-react";
import { fmt, POLICY_LABEL, simClock } from "../lib/format.js";

const STEPS = [
  ["jam", "Jam cluster"],
  ["origin", "Shockwave origin"],
  ["capacity", "Capacity fit"],
  ["ladder", "Counterfactual ladder"],
  ["llm", "LLM reasoning"],
];
const CAUSE_LABEL = {
  capacity_bottleneck: "Capacity bottleneck",
  capacity_bottleneck_under_peak_demand: "Capacity bottleneck under peak demand",
  demand_surge: "Demand surge",
  signal_control: "Signal control",
  inconclusive: "Inconclusive",
};
const RUNG_LABEL = { restore_capacity: "Restore capacity at origin", demand_peak_shift: "Best demand intervention", rl_signal_control: "Best alternative signal policy" };
const nice = (s) => String(s || "").replaceAll("_", " ");

function Section({ title, children, defaultOpen = true, note }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rc-section">
      <button className="rc-section-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />} <b>{title}</b>
        {note && <span className="muted" style={{ marginLeft: "auto", fontSize: 10.5 }}>{note}</span>}
      </button>
      {open && <div className="rc-section-body">{children}</div>}
    </div>
  );
}

// Horizontal bars with 95% CI whiskers for the counterfactual rungs (vehicle-hours recovered).
function LadderBars({ rungs, noise }) {
  const max = Math.max(0.01, ...rungs.map((r) => r.ci_upper_vhr));
  return (
    <div className="ladder">
      {rungs.map((r) => (
        <div key={r.rung_name} className="ladder-row" title={`${r.rung_name}: ${r.mean_recovery_vhr} veh-h [${r.ci_lower_vhr}, ${r.ci_upper_vhr}]`}>
          <span className="ladder-label">#{r.rank} {RUNG_LABEL[r.rung_name] || nice(r.rung_name)}</span>
          <span className="ladder-track">
            <span className="ladder-bar" style={{ width: `${(r.mean_recovery_vhr / max) * 100}%`, background: r.rank === 1 ? "var(--peach)" : "var(--s1)" }} />
            <span className="ladder-ci" style={{ left: `${(r.ci_lower_vhr / max) * 100}%`, width: `${Math.max(0.5, ((r.ci_upper_vhr - r.ci_lower_vhr) / max) * 100)}%` }} />
          </span>
          <span className="num">{fmt(r.mean_recovery_vhr, 2)}</span>
        </div>
      ))}
      <div className="muted" style={{ fontSize: 10.5 }}>Vehicle-hours of congestion removed in the replay (bar = mean, whisker = 95% CI). Noise floor {noise} veh-h.</div>
    </div>
  );
}

export default function RootCausePanel({ rc, onClose }) {
  const [showTrace, setShowTrace] = useState(false);
  const d = rc.diagnosis;
  const llm = rc.llm;
  const a = llm?.analysis;
  const stage = rc.status === "tracing" ? 0 : rc.status === "reasoning" ? 4 : 5;

  return (
    <aside className="rc-drawer" role="dialog" aria-label="Root cause trace">
      <div className="rc-head">
        <div style={{ minWidth: 0 }}>
          <div className="muted" style={{ fontSize: 11 }}>Root cause trace · {rc.point?.name || `cell ${rc.cell}`}</div>
          <h2 style={{ fontSize: 17 }}>Why is this congested?</h2>
        </div>
        <span className="sim-badge">SIMULATED</span>
        <button className="round-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
      </div>

      <div className="rc-steps">
        {STEPS.map(([id, label], i) => {
          const done = rc.status === "error" ? false : i < stage || (rc.status === "done" && (id !== "llm" || llm));
          const active = (rc.status === "tracing" && i < 4) || (rc.status === "reasoning" && id === "llm");
          return (
            <span key={id} className={`rc-step${done ? " done" : ""}${active ? " active" : ""}`}>
              {done ? <CheckCircle2 size={12} /> : active ? <Loader2 size={12} className="spin" /> : <span className="rc-dot" />} {label}
            </span>
          );
        })}
      </div>

      {rc.status === "error" && <div className="explain-box err">{rc.error}</div>}
      {d && !d.found && (
        <div className="explain-box">
          {d.reason}
          {d.immature && <div className="muted" style={{ marginTop: 4 }}>Try again in about {fmt(d.retry_after_sec, 0)} simulated seconds (red ripples are traceable; orange ones are still maturing).</div>}
        </div>
      )}

      {d?.found && (
        <>
          {/* ---- LLM verdict -------------------------------------------------------------------- */}
          {rc.status === "reasoning" && (
            <div className="rc-verdict pending"><Loader2 size={16} className="spin" /> {`Reasoning over the evidence with ${"gpt-oss-120b"} on Groq…`}</div>
          )}
          {a && (
            <div className="rc-verdict">
              <div className="rc-verdict-top">
                <Brain size={16} />
                <span className="tag llm">{CAUSE_LABEL[a.cause_type] || a.cause_type}</span>
                <span className={`tag ${a.confidence === "high" ? "exploit" : a.confidence === "medium" ? "fallback" : "shield"}`}>{a.confidence} confidence</span>
                <span className={`tag ${a.agrees_with_ranking ? "exploit" : "explore"}`}>{a.agrees_with_ranking ? "agrees with ranking" : "qualifies the ranking"}</span>
              </div>
              <h3 className="rc-headline">{a.headline}</h3>
              <p>{a.root_cause}</p>
              <p className="ink2" style={{ fontSize: 12 }}><b>Origin:</b> {a.origin}</p>
              <p className="ink2" style={{ fontSize: 12 }}><b>On the ranking:</b> {a.ranking_comment}</p>
            </div>
          )}

          {a && a.reasoning_steps?.length > 0 && (
            <Section title="Reasoning, step by step">
              <ol className="rc-reasoning">
                {a.reasoning_steps.map((s, i) => (
                  <li key={i}><div>{s.claim}</div><div className="rc-evidence">{s.evidence}</div></li>
                ))}
              </ol>
            </Section>
          )}
          {a?.rl_assessment && (
            <Section title="Role of the RL signal controller">
              <p style={{ margin: 0 }}>{a.rl_assessment}</p>
            </Section>
          )}
          {a?.recommended_actions?.length > 0 && (
            <Section title="Recommended actions">
              <table>
                <thead><tr><th>Action</th><th>Owner</th><th>Expected effect</th></tr></thead>
                <tbody>{a.recommended_actions.map((x, i) => <tr key={i}><td>{x.action}</td><td>{x.owner}</td><td className="ink2">{x.expected_effect}</td></tr>)}</tbody>
              </table>
            </Section>
          )}
          {a?.caveats?.length > 0 && (
            <Section title="Caveats" defaultOpen={false}>
              <ul className="rc-list">{a.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul>
            </Section>
          )}
          {llm && (
            <div className="rc-model muted">
              {llm.provider === "none" ? <><AlertTriangle size={12} /> No LLM reachable; showing the deterministic ranking. {llm.attempts?.map((x) => x.error).join(" · ")}</> : (
                <>
                  {llm.model} ({llm.provider}) · {fmt(llm.latency_ms / 1000, 1)} s
                  {llm.usage?.completion_tokens_details?.reasoning_tokens ? ` · ${llm.usage.completion_tokens_details.reasoning_tokens} reasoning tokens` : ""}
                  {" · "}
                  {llm.ungrounded_numbers?.length ? <span className="err">⚠ numbers not in the evidence: {llm.ungrounded_numbers.join(", ")}</span> : <span>✓ every number cited appears in the evidence</span>}
                  {llm.attempts?.length > 0 && <> · fell back after: {llm.attempts.map((x) => x.model).join(", ")}</>}
                  {llm.reasoning_trace && (
                    <>
                      {" · "}<button className="linkish" onClick={() => setShowTrace(!showTrace)}>{showTrace ? "hide" : "show"} model's reasoning trace</button>
                      {showTrace && <pre className="raw">{llm.reasoning_trace}</pre>}
                    </>
                  )}
                </>
              )}
            </div>
          )}

          {/* ---- deterministic evidence ------------------------------------------------------- */}
          <div className="rc-divider">Evidence from the deterministic pipeline · {POLICY_LABEL[d.policy] || d.policy} run · {simClock(d.sim_time).full} · {fmt(d.runtime_sec, 1)} s</div>

          <Section title="1 · Jam cluster" note="DBSCAN on noisy loop sensors">
            <div className="rc-kv num">
              <span>cells</span><b>{d.jam.tail_cell} → {d.jam.head_cell} ({d.jam.observation_count ?? d.jam.cell_count} congested observations)</b>
              <span>confirmed for</span><b>{fmt(d.jam.age_sec, 0)} s</b>
              <span>extent</span><b>{fmt(d.jam.extent_m, 0)} m</b>
              <span>active</span><b>{simClock(d.jam.start_time_sec).full} – {simClock(d.jam.end_time_sec).full} ({fmt(d.jam.duration_sec, 0)} s)</b>
              <span>mean speed</span><b>{fmt(d.jam.mean_speed_mps, 1)} m/s</b>
            </div>
          </Section>

          <Section title="2 · Shockwave origin" note={d.origin.method}>
            <div className="rc-kv num">
              <span>origin cell</span><b>{d.origin.cell}</b>
              <span>first congested</span><b>{simClock(d.origin.earliest_onset_sec).full}</b>
              <span>backward wave</span><b>{fmt(d.origin.wave_speed_mps, 2)} m/s {d.origin.wave_speed_is_fallback ? "(configured value: no reliable estimate, not evidence)" : `(theory ${d.origin.theoretical_wave_speed_mps})`}</b>
            </div>
            {d.origin.candidates?.length > 1 && (
              <table style={{ marginTop: 6 }}>
                <thead><tr><th className="r">Candidate cell</th><th>Why considered</th><th className="r">Restore removes veh-h (95% CI)</th></tr></thead>
                <tbody>
                  {d.origin.candidates.map((c) => (
                    <tr key={c.cell} style={{ fontWeight: c.cell === d.origin.cell ? 600 : 400 }}>
                      <td className="r num">{c.cell}{c.cell === d.origin.cell ? " ◆" : ""}</td><td className="ink2">{c.kind}</td>
                      <td className="r num">{fmt(c.mean_recovery_vhr, 2)} [{fmt(c.ci_lower_vhr, 2)}, {fmt(c.ci_upper_vhr, 2)}]</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <table style={{ marginTop: 6 }}>
              <thead><tr><th className="r">Cell</th><th>Onset</th><th className="r">Speed m/s</th><th className="r">Flow veh/s</th></tr></thead>
              <tbody>
                {d.origin.evidence_trail.slice(0, 8).map((e) => (
                  <tr key={e.cell_id} style={{ fontWeight: e.is_discharge_origin ? 600 : 400 }}>
                    <td className="r num">{e.cell_id}{e.is_discharge_origin ? " ◆" : ""}</td><td className="num">{simClock(e.timestamp_sec).full}</td>
                    <td className="r num">{fmt(e.mean_speed_mps, 2)}</td><td className="r num">{fmt(e.mean_flow_vps, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section title="3 · Capacity at the origin">
            <div className="rc-kv num">
              <span>effective / nominal</span><b>{d.capacity_at_origin.estimated_capacity} / {d.capacity_at_origin.nominal_capacity} veh/s per lane ({fmt(d.capacity_at_origin.capacity_ratio * 100, 0)}%)</b>
              <span>significant drop</span><b>{d.capacity_at_origin.significant_drop_detected ? "yes" : "no"}</b>
              <span>change points</span><b>{d.capacity_at_origin.change_points.length ? d.capacity_at_origin.change_points.map((t) => simClock(t).full).join(", ") : "none"}</b>
            </div>
            <div className="bar-track" style={{ marginTop: 6, height: 10 }}>
              <span className="bar-fill" style={{ left: 0, width: `${Math.min(100, d.capacity_at_origin.capacity_ratio * 100)}%`, background: d.capacity_at_origin.significant_drop_detected ? "var(--critical)" : "var(--green-2)" }} />
            </div>
          </Section>

          <Section title="4 · Counterfactual ladder" note={`replay ${fmt(d.counterfactual.horizon_sec, 0)} s from ${simClock(d.counterfactual.snapshot_sec).full} · ${d.counterfactual.replicates} replicates`}>
            {d.counterfactual.verdict && (
              <div className={`rc-verdict-banner ${d.counterfactual.verdict.status}`}>
                <b>{d.counterfactual.verdict.status === "conclusive" ? "Conclusive" : d.counterfactual.verdict.status === "tied" ? "Tied" : "Inconclusive"}</b> · {d.counterfactual.verdict.reason}
              </div>
            )}
            <LadderBars rungs={d.counterfactual.rungs} noise={d.counterfactual.noise_floor_vhr} />
            <table style={{ marginTop: 8 }}>
              <thead><tr><th>Signal policy instead of {POLICY_LABEL[d.counterfactual.running_policy]?.split(" (")[0]}</th><th className="r">Recovered veh-h (95% CI)</th></tr></thead>
              <tbody>
                {d.counterfactual.signal_alternatives.map((s) => (
                  <tr key={s.policy}><td>{POLICY_LABEL[s.policy] || s.policy}</td><td className="r num">{fmt(s.mean_recovery_vhr, 2)} [{fmt(s.ci_lower_vhr, 2)}, {fmt(s.ci_upper_vhr, 2)}]</td></tr>
                ))}
              </tbody>
            </table>
            {d.counterfactual.demand_alternatives && (
              <table style={{ marginTop: 8 }}>
                <thead><tr><th>Demand intervention</th><th className="r">Recovered veh-h (95% CI)</th></tr></thead>
                <tbody>
                  {d.counterfactual.demand_alternatives.map((x) => (
                    <tr key={x.intervention}>
                      <td>{x.intervention === "thin_trip_surge" ? `Thin trip surge${Object.keys(d.counterfactual.surge_sources_thinned || {}).length ? ` (entries ${Object.keys(d.counterfactual.surge_sources_thinned).join(", ")})` : " (no surge detected)"}` : "Retime background peak"}</td>
                      <td className="r num">{fmt(x.mean_recovery_vhr, 2)} [{fmt(x.ci_lower_vhr, 2)}, {fmt(x.ci_upper_vhr, 2)}]</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <ul className="rc-list muted" style={{ fontSize: 10.5 }}>{d.counterfactual.assumptions.map((x, i) => <li key={i}>{x}</li>)}</ul>
          </Section>

          <Section title="5 · Ranked hypotheses">
            <table>
              <thead><tr><th>#</th><th>Hypothesis</th><th className="r">Veh-h</th><th className="r">Conf.</th><th>Owner</th></tr></thead>
              <tbody>
                {d.situation.ranked_hypotheses.map((h, i) => (
                  <tr key={i}><td>{i + 1}</td><td>{nice(h.hypothesis_type)}</td><td className="r num">{fmt(h.vehicle_hours_recovered, 2)}</td><td className="r num">{fmt(h.confidence_score, 2)}</td><td className="ink2">{h.responsible_party}</td></tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section title="RL signal controller at these junctions">
            <table>
              <thead><tr><th>Junction</th><th>Where</th><th className="r">Arterial green</th><th className="r">Switches</th><th>Modes</th><th className="r">Shield</th></tr></thead>
              <tbody>
                {d.rl_evidence.map((e) => (
                  <tr key={e.junction}>
                    <td>{e.junction}</td><td className="ink2">{e.position}</td>
                    <td className="r num">{e.arterial_green_share === null ? "–" : `${fmt(e.arterial_green_share * 100, 0)}%`}</td>
                    <td className="r num">{e.switches}</td>
                    <td style={{ fontSize: 11 }}>{Object.entries(e.mode_counts).map(([m, n]) => `${m} ${n}`).join(" · ") || "–"}</td>
                    <td className="r num">{e.shield_overrides}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section title="Validation against the planted scenario" defaultOpen={false} note="hidden from pipeline and LLM">
            <p className="muted" style={{ marginTop: 0, fontSize: 11 }}>{d.validation.note}</p>
            <div className="rc-kv num">
              <span>planted scenario</span><b>{nice(d.validation.scenario)} ({nice(d.validation.scenario_type)})</b>
              <span>planted cells</span><b>{d.validation.planted_windows.map((w) => `${w.cells.join(",")} at ${fmt(w.factor * 100, 0)}%`).join("; ") || "none"}</b>
              <span>origin error</span><b>{d.validation.origin_error_cells ?? "–"} cells</b>
              <span>top hypothesis</span><b>{nice(d.validation.top_hypothesis)} {d.validation.top_matches ? "✓ matches" : `✗ expected ${nice(d.validation.expected_top_hypothesis)}`}</b>
            </div>
          </Section>
        </>
      )}
    </aside>
  );
}
