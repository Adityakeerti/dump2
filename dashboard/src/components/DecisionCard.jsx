import { useState } from "react";
import { Sparkles } from "lucide-react";
import { explainDecision } from "../lib/api.js";
import { fmt, simClock, POLICY_LABEL } from "../lib/format.js";

const MODE_LABEL = { explore: "explore (random)", exploit: "exploit (greedy)", rule: "rule" };

// One signal decision with its full evidence: mode, shield, Q-values, feature attributions, explanation.
export default function DecisionCard({ d, selected, onSelect }) {
  const [llm, setLlm] = useState(null);
  const [busy, setBusy] = useState(false);
  const maxAttr = Math.max(0.001, ...(d.attribution || []).map((a) => Math.abs(a.contribution)));
  const qMin = d.q ? Math.min(...d.q) : 0, qMax = d.q ? Math.max(...d.q) : 1;

  const ask = async () => {
    setBusy(true);
    try { setLlm(await explainDecision(d)); } catch (e) { setLlm({ error: e.message }); }
    setBusy(false);
  };

  return (
    <div className={`decision${selected ? " sel" : ""}`} onClick={onSelect}>
      <div className="decision-top">
        <b className="num">#{d.id}</b>
        <span className="num">{simClock(d.sim_time).full}</span>
        <b>J{d.junction + 1}</b>
        <span>{d.switched ? `→ ${d.executed_phase === 0 ? "arterial" : "cross"} green` : `holds ${d.executed_phase === 0 ? "arterial" : "cross"} green`}</span>
        <span className={`tag ${d.mode}`}>{MODE_LABEL[d.mode] || d.mode}</span>
        {d.shield && <span className="tag shield">shield: {d.shield === "min_green" ? "min green" : "max phase time"}</span>}
        {d.epsilon !== null && d.epsilon !== undefined && <span className="muted num">ε {fmt(d.epsilon, 2)}</span>}
        <span className="muted" style={{ marginLeft: "auto" }}>{POLICY_LABEL[d.policy] || d.policy} · ep {d.episode + 1}</span>
      </div>
      <div className="ink2">{d.text}</div>
      {d.q && (
        <div className="bars num">
          {["keep", "switch"].map((k, i) => (
            <span key={k} style={{ display: "contents" }}>
              <span>Q({k}){d.greedy === i ? " ★" : ""}</span>
              <span className="bar-track"><span className="bar-fill" style={{ left: 0, width: `${qMax === qMin ? 50 : 15 + ((d.q[i] - qMin) / (qMax - qMin)) * 85}%`, background: i ? "var(--peach)" : "var(--green-2)" }} /></span>
              <span>{fmt(d.q[i], 3)}</span>
            </span>
          ))}
        </div>
      )}
      {d.attribution && (
        <div className="bars num" title="gradient × input on Q(switch) − Q(keep); right = pushed towards switching">
          {d.attribution.slice(0, 4).map((a) => {
            const w = (Math.abs(a.contribution) / maxAttr) * 50;
            return (
              <span key={a.feature} style={{ display: "contents" }}>
                <span>{a.feature.replaceAll("_", " ")} <span className="muted">{fmt(a.value, 2)}</span></span>
                <span className="bar-track">
                  <span className="bar-mid" />
                  <span className="bar-fill" style={{ [a.contribution >= 0 ? "left" : "right"]: "50%", width: `${w}%`, background: a.contribution >= 0 ? "var(--peach)" : "var(--green-2)" }} />
                </span>
                <span>{a.contribution >= 0 ? "+" : ""}{fmt(a.contribution, 3)}</span>
              </span>
            );
          })}
        </div>
      )}
      {d.attribution && <div className="muted" style={{ fontSize: 10.5 }}>Attribution: gradient × input on Q(switch) − Q(keep). Bars right of centre pushed towards switching, left towards keeping.</div>}
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <span className="muted num" style={{ fontSize: 11 }}>queues: arterial {fmt(d.art_queue)} · cross {fmt(d.cross_queue)} veh</span>
        <button className="btn ghost" style={{ marginLeft: "auto" }} onClick={(e) => { e.stopPropagation(); ask(); }} disabled={busy}>
          <Sparkles size={13} /> {busy ? "Asking Gemma…" : "Explain with Gemma"}
        </button>
      </div>
      {llm && (
        <div className="explain-box">
          {llm.error ? <span className="err">{llm.error}</span> : (
            <>
              {llm.explanation}
              <div className="muted" style={{ fontSize: 10.5, marginTop: 4 }}>
                {llm.grounded ? `✓ grounded: every number appears in the decision record (${llm.model})` : `⚠ ${llm.note}`}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
