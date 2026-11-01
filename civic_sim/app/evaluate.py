"""Compare the RL policy with the baselines on identical held-out seeds: python -m app.evaluate

Scenarios: one per cause type, a mixed scenario (random 1-2 causes, like training) and a control with no
planted cause (only random potholes and background noise). Every policy sees the same seeds, so the
comparison is paired. Results are written to reports/ and labelled SIMULATED.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from app.config import BASE, CivicConfig, load_config
from app.diagnosis import estimate_onset
from app.dqn import CandidateDQN
from app.env import CivicEnv
from app.policies import build_policy
from app.tracer import feature_names, max_candidates

Z95 = 1.96


def onset_errors(env: CivicEnv) -> list[int]:
    """Estimated minus true onset (ticks) for each identified cause. Evaluation only: reads ground truth."""
    ci = env.cfg.category_index()
    out = []
    for g in env.ground_truth():
        if g["identified_tick"] is None:
            continue
        layer = env.city.layers[g["layer"]]
        est = estimate_onset(env.cfg, env.portal, layer.zone[g["asset"]], sorted(ci[c] for c in layer.cfg.primary),
                             g["identified_tick"])
        if est is not None:
            out.append(est - g["onset_tick"])
    return out


def run_episode(env: CivicEnv, policies: dict, seed: int, scenario: list[str] | None, name: str) -> dict:
    obs = env.reset(seed=seed, scenario=scenario)
    while not env.done:
        obs, _, _, _ = env.step({d: policies[d](obs[d]) for d in env.departments}, policy=name)
    return env.episode_metrics() | {"onset_errors": onset_errors(env)}


def scenarios(cfg: CivicConfig) -> dict[str, list[str] | None]:
    out: dict[str, list[str] | None] = {c.id: [c.id] for c in cfg.causes}
    out["mixed"] = None
    out["control"] = []
    return out


def mean_ci(xs: list[float]) -> tuple[float, float]:
    if not xs:
        return float("nan"), float("nan")
    a = np.asarray(xs, dtype=float)
    half = Z95 * a.std(ddof=1) / math.sqrt(len(a)) if len(a) > 1 else 0.0
    return float(a.mean()), float(half)


def summarise(eps: list[dict]) -> dict:
    causes = sum(e["causes"] for e in eps)
    per_episode = {k: [e[k] for e in eps] for k in ("reward", "complaints", "identified", "false_repairs")}
    tti = [t for e in eps for t in e["ticks_to_identify"]]
    out = {"episodes": len(eps), "causes": causes,
           "identified_rate": round(sum(e["identified"] for e in eps) / causes, 3) if causes else None,
           "fixed_rate": round(sum(e["fixed"] for e in eps) / causes, 3) if causes else None}
    for k, xs in {"ticks_to_identify": tti, "onset_abs_error": [abs(x) for e in eps for x in e["onset_errors"]],
                  "complaints": [e["complaints"] for e in eps],
                  "false_repairs": [e["false_repairs"] for e in eps], "symptom_actions": [e["symptom_actions"] for e in eps],
                  "inspections": [e["inspections"] for e in eps], "reward": [e["reward"] for e in eps]}.items():
        m, h = mean_ci(xs)
        out[k] = {"mean": round(m, 2), "ci95": round(h, 2), "n": len(xs)}
    out["per_episode"] = per_episode
    return out


def paired(results: dict, a: str, b: str) -> dict:
    """a - b per scenario on the same seeds (paired), mean and 95% interval of the per-episode differences."""
    out = {}
    for sname, per in results.items():
        if a not in per or b not in per:
            continue
        out[sname] = {}
        for k in ("reward", "complaints", "identified", "false_repairs"):
            m, h = mean_ci([x - y for x, y in zip(per[a]["per_episode"][k], per[b]["per_episode"][k])])
            out[sname][k] = {"mean": round(m, 2), "ci95": round(h, 2), "n": len(per[a]["per_episode"][k])}
    return out


def evaluate(cfg: CivicConfig, agent: CandidateDQN | None, episodes: int | None = None) -> dict:
    n_ep = episodes or cfg.evaluation.episodes_per_scenario
    env = CivicEnv(cfg)
    results: dict = {}
    for sname, scen in scenarios(cfg).items():
        results[sname] = {}
        for pname in cfg.evaluation.policies:
            if pname == "rl" and agent is None:
                continue
            eps = []
            for i in range(n_ep):
                seed = cfg.evaluation.seed_offset + i
                pol = {d: build_policy(pname, cfg, agent, seed + j) for j, d in enumerate(env.departments)}
                eps.append(run_episode(env, pol, seed, scen, pname))
            results[sname][pname] = summarise(eps)
    return results


def fmt(v: dict | float | None) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, dict):
        return "n/a" if v["n"] == 0 else f"{v['mean']:.2f} ± {v['ci95']:.2f}"
    return f"{v:.3f}"


def write_report(cfg: CivicConfig, results: dict, meta: dict | None, path: Path) -> None:
    lines = [
        "# Civic RL results: root-cause investigation policy",
        "",
        "> **SIMULATED.** Synthetic 6x6-block city, planted causes, synthetic residents. Nothing here is a",
        "> measurement of a real city. ± is a 95% normal-approximation interval over episodes.",
        "",
        f"- Config hash: `{cfg.config_hash()[:16]}`",
        f"- Held-out seeds: {cfg.evaluation.seed_offset} .. {cfg.evaluation.seed_offset + cfg.evaluation.episodes_per_scenario - 1} "
        "(training used seeds from `seed` upward; ranges do not overlap)",
    ]
    if meta:
        lines += [f"- Checkpoint: {meta['episodes']} training episodes, {meta['updates']} gradient updates, "
                  f"algorithm `{meta['algorithm']}`"]
    lines += [
        "",
        "Metrics: **identified** = share of planted causes that an inspection or repair confirmed within the episode; "
        "**fixed** = share removed; **ticks to identify** = ticks from onset to confirmation (1 tick = "
        f"{cfg.tick_hours} h); **onset error** = |estimated − true| start tick of each identified cause (CUSUM change point, "
        "see diagnosis.py); **complaints** = all complaints in the episode (lower is better); **false repairs** = "
        "repairs on healthy assets; **symptom actions** = pothole patches and traffic marshals.",
        "",
    ]
    for sname, per in results.items():
        lines += [f"## Scenario: `{sname}`", "",
                  "| Policy | Identified | Fixed | Ticks to identify | Onset error (ticks) | Complaints | False repairs | Symptom actions | Inspections | Reward |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for pname, s in per.items():
            lines.append(f"| {pname} | {fmt(s['identified_rate'])} | {fmt(s['fixed_rate'])} | {fmt(s['ticks_to_identify'])} | "
                         f"{fmt(s['onset_abs_error'])} | {fmt(s['complaints'])} | {fmt(s['false_repairs'])} | {fmt(s['symptom_actions'])} | "
                         f"{fmt(s['inspections'])} | {fmt(s['reward'])} |")
        lines.append("")
    for base in ("tracer", "complaint_count"):
        diff = paired(results, "rl", base)
        if not diff:
            continue
        lines += [f"## Paired difference: rl − {base} (same seeds)", "",
                  "An interval that excludes 0 is a difference at roughly the 95% level. Reward and identified: higher is "
                  "better for rl. Complaints and false repairs: lower is better for rl.", "",
                  "| Scenario | Δ reward | Δ complaints | Δ identified causes / episode | Δ false repairs |", "|---|---|---|---|---|"]
        for sname, d in diff.items():
            lines.append(f"| {sname} | {fmt(d['reward'])} | {fmt(d['complaints'])} | {fmt(d['identified'])} | {fmt(d['false_repairs'])} |")
        lines.append("")
    if meta and meta.get("curve"):
        lines += ["## Training curve (blocks of 50 episodes)", "", "| Episodes | Teacher-forced | Mean reward | Identified | Complaints |",
                  "|---|---|---|---|---|"]
        for c in meta["curve"]:
            lines.append(f"| {c['episodes']} | {'yes' if c['demo'] else 'no'} | {c['mean_reward']} | {c['identified_rate']} | {c['mean_complaints']} |")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--episodes", type=int, default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    ckpt = BASE / cfg.rl.checkpoint_path
    agent, meta = None, None
    if ckpt.is_file():
        agent = CandidateDQN(cfg.rl, len(feature_names(cfg)), max_candidates(cfg), cfg.seed)
        meta = agent.load(ckpt)
        if meta.get("config_hash") != cfg.config_hash():
            print("WARNING: checkpoint was trained with a different config")
    else:
        print(f"no checkpoint at {ckpt}; evaluating baselines only")
    results = evaluate(cfg, agent, args.episodes)
    (BASE / cfg.evaluation.json_path).parent.mkdir(parents=True, exist_ok=True)
    (BASE / cfg.evaluation.json_path).write_text(json.dumps(
        {"simulated": True, "results": results, "paired_rl_minus_tracer": paired(results, "rl", "tracer")}, indent=1))
    write_report(cfg, results, meta, BASE / cfg.evaluation.report_path)
    for sname, per in results.items():
        print(sname)
        for pname, s in per.items():
            print(f"  {pname:16s} identified {fmt(s['identified_rate'])}  complaints {fmt(s['complaints'])}  "
                  f"false_repairs {fmt(s['false_repairs'])}  reward {fmt(s['reward'])}")


if __name__ == "__main__":
    main()
