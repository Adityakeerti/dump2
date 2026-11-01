"""LLM reasoning over a deterministic root-cause trace from the live twin.

The twin's pipeline (jam clustering, shockwave back-tracing, capacity fit, counterfactual ladder with real signal
controllers) produces the evidence and the ranking. The LLM (Groq `openai/gpt-oss-120b` by default, a reasoning
model) only explains it: it reasons step by step from that evidence, states whether it agrees with the ranking,
assesses the RL signal controller's role and proposes actions. Guardrails:
  * the planted scenario name and ground truth are removed before the call (no answer leakage);
  * a strict JSON schema shapes the answer;
  * every number the model writes is checked against the evidence and unmatched ones are flagged;
  * fallback chain: Groq primary -> Groq fallback -> local Gemma -> deterministic summary.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

CAUSE_TYPES = ["capacity_bottleneck", "capacity_bottleneck_under_peak_demand", "demand_surge", "signal_control", "inconclusive"]

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "headline": {"type": "string"},
        "root_cause": {"type": "string"},
        "cause_type": {"type": "string", "enum": CAUSE_TYPES},
        "origin": {"type": "string"},
        "agrees_with_ranking": {"type": "boolean"},
        "ranking_comment": {"type": "string"},
        "reasoning_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"claim": {"type": "string"}, "evidence": {"type": "string"}},
                "required": ["claim", "evidence"],
            },
        },
        "rl_assessment": {"type": "string"},
        "recommended_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"action": {"type": "string"}, "owner": {"type": "string"}, "expected_effect": {"type": "string"}},
                "required": ["action", "owner", "expected_effect"],
            },
        },
        "caveats": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["headline", "root_cause", "cause_type", "origin", "agrees_with_ranking", "ranking_comment",
                 "reasoning_steps", "rl_assessment", "recommended_actions", "caveats", "confidence"],
}

SYSTEM = """You are a senior traffic engineer reviewing the output of a deterministic root-cause pipeline run on a
SIMULATED digital twin of an urban arterial (cell transmission model). You explain; you do not invent data.

How the evidence was produced:
1. Jam cluster: DBSCAN over noisy loop-sensor speeds below the congestion threshold.
2. Origin: shockwave back-tracing gives the jam's downstream-most discharge front (origin.traced_front_cell). When
   queues from two bottlenecks merge, that front can be the wrong one, so several candidates (traced front, internal
   discharge fronts, junction stop lines in the jam) each get a capacity-restore replay (origin.candidates); the
   candidate that removes clearly the most delay becomes origin.cell. Usually within +-1 cell of the bottleneck.
3. Capacity at origin: effective vs nominal capacity (capacity_ratio), with change points; a significant drop means a
   physical restriction (lane blockage, incident, works) rather than only too many vehicles.
4. Counterfactual ladder: the twin is replayed from a snapshot taken before the jam, with the real signal controllers
   running, under interventions: restore_capacity (clear restrictions around the origin), demand_peak_shift (retime the
   background demand peak, or thin a detected trip surge at an entry; counterfactual.demand_alternatives shows both),
   rl_signal_control (best alternative signal policy, incl. the reinforcement-learning DQN).
   Recovery is vehicle-hours of congestion removed, with a 95% CI over demand-perturbation replicates. Rungs are
   interventions of different size: a larger recovery means more relief, not automatically more blame.
5. A deterministic ranking (by recovery) produced the situation's hypotheses.
6. rl_evidence: what the RL signal controller did at the junctions in and around the jam (arterial green share,
   switches, explore/exploit/shield counts, mean Q-margin, recent decisions).

7. counterfactual.verdict is the ladder's own judgement: "conclusive" (top rung separated and above the minimum
   effect), "tied" (top two 95% intervals overlap) or "inconclusive" (largest effect below min_effect_vhr).
   jam.age_sec says how long the twin has confirmed this jam; origin.wave_speed_is_fallback=true means the wave
   speed is the configured value, not a measurement, so it is not evidence.

Cell ids increase downstream along the arterial. Your job:
- Identify the most likely root cause of THIS congestion, reasoning step by step from specific evidence fields.
- Say whether you agree with the deterministic top-ranked hypothesis. If confidence intervals overlap, say the
  ladder cannot separate them. Causes can coexist (e.g. a capacity bottleneck under peak demand).
- Assess the RL signal controller: did its decisions cause or worsen the jam, and would a different policy help?
  Use the signal-alternative recoveries and rl_evidence.
- Recommend concrete operator actions with an owner.
- List caveats (simulated data, sensor noise, origin +-1 cell, replay horizon, intervention sizes).
Calibrate confidence: "high" only if the verdict is "conclusive" AND the physical evidence (capacity drop, origin)
points the same way; with "tied" use at most "medium" and name the competing causes; with "inconclusive" use "low"
and say what more data or time would resolve it. 95% intervals cover demand-perturbation noise only.
Quote numbers exactly as they appear in the evidence. Never introduce numbers that are not in the evidence."""


def _load_key() -> str | None:
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    here = Path(__file__).resolve()
    for env in (here.parents[3] / ".env", here.parents[2] / ".env"):  # SmartCity/.env, Project/.env
        if env.is_file():
            for line in env.read_text().splitlines():
                if line.strip().startswith("GROQ_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def compact_evidence(d: dict[str, Any], topology: dict[str, Any] | None) -> dict[str, Any]:
    """Evidence for the LLM: no ground truth, no scenario name, no repo action-template strings."""
    cf = {k: v for k, v in d["counterfactual"].items() if k != "scenario_name"}
    sit = d["situation"]
    hyps = [{k: h[k] for k in ("hypothesis_type", "target_cell", "vehicle_hours_recovered", "ci_lower", "ci_upper",
                                "confidence_score", "recommended_action", "responsible_party")} for h in sit["ranked_hypotheses"]]
    corridor = None
    if topology:
        cpl = topology["cells_per_link"]
        corridor = {
            "arterial_cells": f"0-{len(topology['arterial_cells']) - 1}, {cpl} cells per link, flow towards higher ids",
            "junction_stop_lines": {f"J{j['id'] + 1}": j["arterial_approach"] for j in topology["geometry"]["junctions"]},
            "simulated_cell_length_m": topology["geometry"]["cell_length"][0],
            "road": (topology["geometry"].get("streets") or {}).get("arterial_name"),
        }
    return {
        "clicked_cell": d["cell"],
        "sim_time_sec": d["sim_time"],
        "signal_policy_running": d["policy"],
        "corridor": corridor,
        "jam": {k: d["jam"].get(k) for k in ("tail_cell", "head_cell", "observation_count", "age_sec", "start_time_sec",
                                             "end_time_sec", "extent_m", "duration_sec", "mean_speed_mps")},
        "origin": {**{k: v for k, v in d["origin"].items() if k != "evidence_trail"},
                   "evidence_trail": [{k: e[k] for k in ("cell_id", "timestamp_sec", "mean_speed_mps", "mean_flow_vps", "is_discharge_origin")}
                                      for e in d["origin"]["evidence_trail"][:8]]},
        "capacity_at_origin": d["capacity_at_origin"],
        "counterfactual": cf,
        "ranked_hypotheses": hyps,
        "rl_evidence": [{**e, "recent_decisions": e["recent_decisions"][-3:]} for e in d["rl_evidence"]],
    }


NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?\s?%?")
DASHES = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-"})
ALWAYS_OK = {95.0}  # the "95%" confidence level is a method constant, not a data value


def ungrounded_numbers(analysis: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    have: list[float] = []
    for tok in NUM.findall(json.dumps(evidence, ensure_ascii=False).translate(DASHES)):
        have.append(abs(float(tok.rstrip("% "))))
    text = json.dumps({k: v for k, v in analysis.items() if k not in ("cause_type", "confidence", "agrees_with_ranking")},
                      ensure_ascii=False).translate(DASHES)
    bad = []
    for raw in NUM.findall(text):
        tok = raw.replace(" ", "")
        pct = tok.endswith("%")
        v = abs(float(tok.rstrip("%")))  # sign-insensitive: ranges like "1.08-1.21" split into "1.08" and "-1.21"
        if v in ALWAYS_OK:
            continue
        cands = [v, v / 100] if pct else [v]
        if abs(v) <= 10 and float(v).is_integer() and not pct:
            continue  # junction / step / list indices
        # rounding-level tolerance: half a unit in the last written digit, or 2% relative
        decimals = len(tok.rstrip("%").split(".")[1]) if "." in tok else 0
        unit = 0.5 * 10 ** (-decimals)
        if not any(abs(c - h) <= max(unit / (100 if (pct and c != v) else 1), abs(h) * 0.02) for c in cands for h in have):
            bad.append(tok)
    return sorted(set(bad))


def deterministic_summary(d: dict[str, Any]) -> dict[str, Any]:
    top = d["situation"]["top_hypothesis"] or {}
    cap = d["capacity_at_origin"]
    return {
        "headline": f"Top-ranked hypothesis: {top.get('hypothesis_type')} at cell {d['origin']['cell']}",
        "root_cause": f"Deterministic ranking only (no LLM available). Capacity ratio at origin {cap['capacity_ratio']}.",
        "cause_type": "inconclusive",
        "origin": f"cell {d['origin']['cell']}",
        "agrees_with_ranking": True,
        "ranking_comment": "No LLM review was possible; showing the pipeline's own ranking.",
        "reasoning_steps": [],
        "rl_assessment": "",
        "recommended_actions": [{"action": top.get("recommended_action", ""), "owner": top.get("responsible_party", ""), "expected_effect": ""}],
        "caveats": ["LLM unavailable"],
        "confidence": "low",
    }


async def reason(
    client: httpx.AsyncClient,
    diagnosis: dict[str, Any],
    topology: dict[str, Any] | None,
    rc_cfg: dict[str, Any],
    local_llm_url: str,
    local_model: str,
) -> dict[str, Any]:
    evidence = compact_evidence(diagnosis, topology)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "Evidence (JSON):\n" + json.dumps(evidence, separators=(",", ":"))}]
    key = _load_key()
    attempts: list[dict[str, Any]] = []
    for model in (rc_cfg["model"], rc_cfg["fallback_model"]):
        if not key:
            attempts.append({"model": model, "error": "GROQ_API_KEY not set"})
            break
        t0 = time.perf_counter()
        try:
            res = await client.post(
                f"{rc_cfg['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": rc_cfg["temperature"],
                    "reasoning_effort": rc_cfg["reasoning_effort"],
                    "max_completion_tokens": rc_cfg["max_tokens"],
                    "response_format": {"type": "json_schema", "json_schema": {"name": "root_cause", "strict": True, "schema": SCHEMA}},
                },
                timeout=rc_cfg["timeout_sec"],
            )
            body = res.json()
            if res.status_code != 200:
                raise RuntimeError(str(body.get("error", body))[:300])
            msg = body["choices"][0]["message"]
            analysis = json.loads(msg["content"])
            return {
                "analysis": analysis,
                "provider": "groq",
                "model": model,
                "reasoning_trace": msg.get("reasoning"),
                "usage": body.get("usage"),
                "latency_ms": round((time.perf_counter() - t0) * 1000),
                "ungrounded_numbers": ungrounded_numbers(analysis, evidence),
                "attempts": attempts,
                "evidence_sent": evidence,
            }
        except Exception as exc:
            attempts.append({"model": model, "error": f"{type(exc).__name__}: {exc}"[:300]})

    # local Gemma fallback (smaller context: drop the trail and decisions)
    small = {**evidence, "origin": {k: v for k, v in evidence["origin"].items() if k != "evidence_trail"},
             "rl_evidence": [{k: v for k, v in e.items() if k != "recent_decisions"} for e in evidence["rl_evidence"]]}
    t0 = time.perf_counter()
    try:
        res = await client.post(
            f"{local_llm_url}/chat/completions",
            json={"model": local_model, "temperature": 0.2, "max_tokens": 900,
                  "messages": [messages[0], {"role": "user", "content": "Evidence (JSON):\n" + json.dumps(small, separators=(",", ":"))}],
                  "response_format": {"type": "json_schema", "json_schema": {"name": "root_cause", "schema": SCHEMA}}},
            timeout=rc_cfg["timeout_sec"],
        )
        analysis = json.loads(res.json()["choices"][0]["message"]["content"])
        return {"analysis": analysis, "provider": "local", "model": local_model, "reasoning_trace": None,
                "usage": res.json().get("usage"), "latency_ms": round((time.perf_counter() - t0) * 1000),
                "ungrounded_numbers": ungrounded_numbers(analysis, small), "attempts": attempts, "evidence_sent": small}
    except Exception as exc:
        attempts.append({"model": local_model, "error": f"{type(exc).__name__}: {exc}"[:300]})
    return {"analysis": deterministic_summary(diagnosis), "provider": "none", "model": None, "reasoning_trace": None,
            "usage": None, "latency_ms": None, "ungrounded_numbers": [], "attempts": attempts, "evidence_sent": evidence}
