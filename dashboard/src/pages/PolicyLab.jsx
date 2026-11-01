import { useMemo, useState } from "react";
import { Power } from "lucide-react";
import LineChart from "../components/LineChart.jsx";
import Heatmap from "../components/Heatmap.jsx";
import DecisionCard from "../components/DecisionCard.jsx";
import { twinControl } from "../lib/api.js";
import { fmt, POLICY_LABEL, POLICY_VAR, simClock } from "../lib/format.js";

const MODE_FILTERS = [
  ["all", "All"], ["explore", "Explore"], ["exploit", "Exploit"], ["shield", "Shield overrides"], ["switch", "Phase switches"],
];

const KPI_ROWS = [
  ["mean_system_vehicles", "Mean vehicles in system", 1, "lower is better"],
  ["max_system_vehicles", "Peak vehicles in system", 0, ""],
  ["jam_cell_min", "Congested cell-minutes", 1, "arterial cells below the congestion threshold"],
  ["mean_delay_sec", "Mean car-cluster delay (s)", 0, "travel time minus free-flow time"],
  ["platoons_done", "Car clusters finished", 0, ""],
  ["throughput", "Vehicles exited", 0, ""],
  ["switches", "Phase switches", 0, ""],
  ["shield_overrides", "Shield overrides", 0, "safety rule changed the proposed action"],
  ["explore_frac", "Random draws (fraction)", 2, "DQN only: share of actions drawn at random"],
  ["explore_effective_frac", "Effective exploration", 2, "DQN only: random, different from greedy, not overridden by the shield"],
  ["mean_loss", "Mean TD loss", 3, "DQN only"],
];

export default function PolicyLab({ twin }) {
  const { topology, state, decisions, history, episodes, finished } = twin;
  const [mode, setMode] = useState("all");
  const [sel, setSel] = useState(null);
  const learning = state?.learning;
  const policies = topology?.policies || [];

  const shownDecisions = useMemo(() => {
    const f = decisions.filter((d) =>
      mode === "all" ? true : mode === "shield" ? d.shield : mode === "switch" ? d.switched : d.mode === mode);
    return f.slice(-60).reverse();
  }, [decisions, mode]);

  const xLabels = episodes.map((e) => e.episode + 1);
  const series = (key) => policies.map((p) => ({
    key: p, label: POLICY_LABEL[p].split(" (")[0], color: POLICY_VAR[p], values: episodes.map((e) => e.policies?.[p]?.[key] ?? null),
  }));
  const dqnKpi = (e, k) => e.policies?.[topology?.learning_policy]?.[k] ?? null;
  const explore = [
    { key: "eps", label: "ε", color: "var(--s1)", values: episodes.map((e) => e.epsilon) },
    { key: "draw", label: "random draws", color: "var(--s2)", values: episodes.map((e) => dqnKpi(e, "explore_frac")) },
    { key: "eff", label: "effective", color: "var(--s3)", values: episodes.map((e) => dqnKpi(e, "explore_effective_frac")) },
  ];

  if (!state || !topology) return <div className="empty">Connecting to the digital twin…</div>;
  const sel_d = decisions.find((d) => d.id === sel);

  return (
    <div className="col">
      <div className="page-head">
        <div>
          <h1>Policy Lab</h1>
          <p>
            The Double DQN controls all {topology.num_junctions} junction signals and learns online with ε-greedy exploration
            (ε decays per episode). Fixed-time, longest-queue and max-pressure run in lockstep on identical demand, scenario and
            agent trips, so every episode is a like-for-like comparison. A safety shield (min green {topology.shield.min_green_sec}s,
            max phase {topology.shield.max_phase_sec}s) sits outside the policy.
          </p>
        </div>
        <button className={`btn${learning?.enabled ? "" : " peach"}`} onClick={() => twinControl({ learning: !learning?.enabled })}>
          <Power size={13} /> {learning?.enabled ? "Learning on — click for greedy-only" : "Greedy only — click to resume learning"}
        </button>
      </div>

      <div className="kpis" style={{ gridTemplateColumns: "repeat(6, minmax(0,1fr))" }}>
        {[
          ["Episode", `${state.episode + 1}`, `${simClock(state.sim_time).full} · ${fmt((state.sim_time / state.episode_duration_sec) * 100, 0)}% done`],
          ["ε now", fmt(learning.epsilon, 3), `next: ${learning.epsilon_schedule.slice(1, 4).map((x) => fmt(x, 2)).join(" → ")}`],
          ["Random actions (last 60 s)", `${fmt(learning.recent_explore_rate * 100, 0)}%`, "observed exploration rate"],
          ["Replay buffer", learning.replay_size, "transitions (1 per junction-step)"],
          ["Gradient updates", learning.updates, "Double DQN, target net sync"],
          ["TD loss (last)", fmt(learning.last_loss, 3), "MSE on scaled reward"],
        ].map(([l, v, s]) => (
          <div className="kpi" key={l}><div className="kpi-label">{l}</div><div className="kpi-value num">{v}</div><div className="kpi-sub">{s}</div></div>
        ))}
      </div>

      <div className="grid-2">
        <div className="panel">
          <div className="panel-head"><h2>Learning curve: mean vehicles in system per episode</h2></div>
          <LineChart series={series("mean_system_vehicles")} xLabels={xLabels} yLabel="Mean vehicles in system" />
        </div>
        <div className="panel">
          <div className="panel-head"><h2>Mean car-cluster delay per episode (s)</h2></div>
          <LineChart series={series("mean_delay_sec")} xLabels={xLabels} yLabel="Mean delay seconds" digits={0} />
        </div>
      </div>

      <div className="grid-2">
        <div className="panel">
          <div className="panel-head"><h2>Exploration schedule vs observed</h2></div>
          <LineChart series={explore} xLabels={xLabels} yLabel="Fraction of actions" digits={2} height={180} />
          <p className="muted" style={{ fontSize: 11 }}>
            Random draws track ε by construction. <b>Effective</b> exploration counts only random actions that differed from the greedy
            choice and were not overridden by the safety shield (min green / max phase), i.e. the exploration that actually changed the signals.
          </p>
        </div>
        <div className="panel">
          <div className="panel-head"><h2>This episode so far</h2><span className="sim-badge">SIMULATED</span></div>
          <div className="scroll">
            <table>
              <thead><tr><th>Metric</th>{policies.map((p) => <th key={p} className="r"><i style={{ display: "inline-block", width: 10, height: 3, background: POLICY_VAR[p], marginRight: 4, verticalAlign: "middle" }} />{POLICY_LABEL[p].split(" (")[0]}</th>)}</tr></thead>
              <tbody>
                {KPI_ROWS.map(([key, label, d, hint]) => {
                  const vals = policies.map((p) => state.kpis[p]?.[key]);
                  const lowerBetter = ["mean_system_vehicles", "max_system_vehicles", "jam_cell_min", "mean_delay_sec"].includes(key);
                  const best = lowerBetter ? Math.min(...vals.filter((v) => v !== null && v !== undefined)) : null;
                  return (
                    <tr key={key} title={hint}>
                      <td>{label}</td>
                      {vals.map((v, i) => <td key={i} className="r num" style={{ fontWeight: lowerBetter && v === best ? 600 : 400 }}>{fmt(v, d)}{lowerBetter && v === best ? " ✓" : ""}</td>)}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="grid-2" style={{ alignItems: "start" }}>
        <div className="panel">
          <div className="panel-head">
            <h2>Decision stream · {POLICY_LABEL[state.policy]}</h2>
            <span className="muted" style={{ fontSize: 11 }}>switch the run in Dashboard → Signal policy</span>
          </div>
          <div className="filters">
            {MODE_FILTERS.map(([id, l]) => <button key={id} className={`chip${mode === id ? " on" : ""}`} onClick={() => setMode(id)}>{l}</button>)}
          </div>
          <div style={{ display: "grid", gap: 8, maxHeight: 760, overflow: "auto" }}>
            {shownDecisions.length === 0 && <div className="empty">No decisions match yet.</div>}
            {shownDecisions.map((d) => <DecisionCard key={d.id} d={d} selected={d.id === sel} onSelect={() => setSel(d.id)} />)}
          </div>
        </div>
        <div className="col">
          <div className="panel">
            <div className="panel-head"><h2>Time-space diagram (arterial speed)</h2></div>
            <Heatmap history={history} topology={topology} />
          </div>
          <div className="panel">
            <div className="panel-head"><h2>Junctions now</h2></div>
            <table>
              <thead><tr><th>Junction</th><th>Phase</th><th className="r">In phase</th><th className="r">Arterial q</th><th className="r">Cross q</th><th className="r">Last switch</th></tr></thead>
              <tbody>
                {state.junctions.map((j) => (
                  <tr key={j.id}>
                    <td>J{j.id + 1}</td>
                    <td>{j.phase === 0 ? "arterial green" : "cross green"}</td>
                    <td className="r num">{fmt(j.time_in_phase, 0)}s</td>
                    <td className="r num">{fmt(j.art_queue)}</td>
                    <td className="r num">{fmt(j.cross_queue)}</td>
                    <td className="r num">{j.last_decision ? <button className="chip" onClick={() => setSel(j.last_decision)}>#{j.last_decision}</button> : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="panel">
            <div className="panel-head"><h2>Car clusters and the decisions that released them</h2></div>
            <div className="scroll" style={{ maxHeight: 340 }}>
              <table>
                <thead><tr><th>#</th><th>Cluster</th><th className="r">Travel</th><th className="r">Delay</th><th>Junction passes (wait ← decision)</th></tr></thead>
                <tbody>
                  {finished.slice(-40).reverse().map((p) => (
                    <tr key={`${p.id}-${p.seq}`}>
                      <td className="num">{p.id}</td>
                      <td>{p.cluster}<div className="muted" style={{ fontSize: 10.5 }}>{p.intent} · {fmt(p.vehicles, 0)} veh</div></td>
                      <td className="r num">{fmt(p.travel_sec, 0)}s</td>
                      <td className="r num">{fmt(p.delay_sec, 0)}s</td>
                      <td style={{ fontSize: 11 }}>
                        {p.passes.length === 0 && <span className="muted">no signal on route</span>}
                        {p.passes.map((x, i) => (
                          <span key={i} style={{ marginRight: 6, whiteSpace: "nowrap" }}>
                            J{x.junction + 1} {fmt(x.wait_sec, 0)}s
                            {x.released_by && <> ← <button className="chip" style={{ padding: "0 6px" }} onClick={() => setSel(x.released_by)}>#{x.released_by}</button></>}
                          </span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {finished.length === 0 && <div className="empty">No car cluster has finished yet in this episode.</div>}
            </div>
            {sel && (
              <div style={{ marginTop: 10 }}>
                {sel_d ? <DecisionCard d={sel_d} selected /> : <div className="muted">Decision #{sel} is older than the {decisions.length} decisions kept in the browser.</div>}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head"><h2>Episode history</h2><span className="muted">{episodes.length} episodes · persisted with the DQN checkpoint</span></div>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Ep</th><th>Scenario</th><th className="r">ε</th><th className="r">Agent trips</th>{policies.map((p) => <th key={p} className="r">{POLICY_LABEL[p].split(" (")[0]} veh / delay</th>)}</tr>
            </thead>
            <tbody>
              {[...episodes].reverse().map((e) => (
                <tr key={e.episode}>
                  <td className="num">{e.episode + 1}</td>
                  <td>{e.scenario.replaceAll("_", " ")}</td>
                  <td className="r num">{fmt(e.epsilon, 2)}{e.learning ? "" : " (greedy)"}</td>
                  <td className="r num">{e.agent_trips}</td>
                  {policies.map((p) => <td key={p} className="r num">{fmt(e.policies[p]?.mean_system_vehicles)} / {fmt(e.policies[p]?.mean_delay_sec, 0)}s</td>)}
                </tr>
              ))}
            </tbody>
          </table>
          {episodes.length === 0 && <div className="empty">The first episode completes after {fmt(topology.episode_duration_sec / 60, 0)} simulated minutes.</div>}
        </div>
      </div>
    </div>
  );
}
