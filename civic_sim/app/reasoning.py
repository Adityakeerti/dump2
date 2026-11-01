"""LLM reasoning over the civic simulator's deterministic evidence (same pattern as city_sim/app/root_cause.py).

Two uses:
  * root_cause(): a reasoning model (Groq `openai/gpt-oss-120b` by default) reviews one confirmed root cause or one
    hypothesis: the symptom chain, the tracer's scores, the crews' work log and the departments' policy. It explains
    and critiques; it does not decide. Confirmation still comes only from a field inspection or repair.
  * explain_action(): local Gemma explains one crew decision in plain language from the candidate features and
    Q-values that the policy actually saw.

Guardrails (as in city_sim):
  * evidence is built from PUBLIC data only (portal, work log, maps, mechanism table); ground truth is never sent;
  * strict JSON schema for the root-cause answer;
  * every number the model writes is checked against the evidence; unmatched numbers are returned in
    `ungrounded_numbers` (root cause) or replace the text with the deterministic one (decision explanations);
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

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "headline": {"type": "string"},
        "root_cause": {"type": "string"},
        "where_it_started": {"type": "string"},
        "mechanism": {"type": "string"},
        "agrees_with_system": {"type": "boolean"},
        "system_comment": {"type": "string"},
        "reasoning_steps": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": False,
                      "properties": {"claim": {"type": "string"}, "evidence": {"type": "string"}},
                      "required": ["claim", "evidence"]},
        },
        "alternatives_considered": {"type": "array", "items": {"type": "string"}},
        "policy_assessment": {"type": "string"},
        "recommended_actions": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": False,
                      "properties": {"action": {"type": "string"}, "owner": {"type": "string"}, "expected_effect": {"type": "string"}},
                      "required": ["action", "owner", "expected_effect"]},
        },
        "caveats": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["headline", "root_cause", "where_it_started", "mechanism", "agrees_with_system", "system_comment",
                 "reasoning_steps", "alternatives_considered", "policy_assessment", "recommended_actions", "caveats", "confidence"],
}

SYSTEM = """You are a senior municipal operations analyst reviewing the output of a deterministic root-cause system run
on a SIMULATED city (a 6x6 grid of blocks, 9 wards, 360 synthetic residents). You explain and critique; you do not
invent data.

How the evidence was produced:
1. Residents report what they see on their own block to a complaint portal. Reporting is noisy: personas differ,
   some wards under-report, and every category has background complaints with no underlying fault.
2. The portal routes each complaint to the Municipal Corporation (roads, water, sewer, waste, streetlights) or the
   Police (crime, traffic). A fault in one department's asset can produce complaints that go to the other department
   (for example a streetlight feeder fault leads to theft complaints that reach the Police).
3. Infrastructure maps are public: water and sewer are trees (a water leak affects blocks downstream of it; a sewer
   blockage backs up into blocks upstream of it, NOT at the blocked segment), waste routes and feeder circuits cover
   fixed groups of blocks, a crime source affects blocks within a small radius. `mechanism_table` lists which
   complaint categories each asset type can cause.
4. A deterministic tracer scores every asset: coverage (share of matching complaints inside the asset's zone), lift
   (complaint density in the zone vs the city average), root_first (the asset's own area reported first).
5. Each tick, each department's policy (named in `policy`) chooses one action: inspect an asset, repair it, or wait.
   A root cause is CONFIRMED only when a field inspection or repair found the fault. Inspections can miss a real
   fault (miss probabilities are in `mechanism_table`), but never report a fault that is not there.
6. "started.estimated" is a CUSUM change point on the zone's primary complaints: when reports rose above background,
   not necessarily when the fault began.
7. episode_so_far gives the crews' totals: false_repairs are repairs on healthy assets, symptom_actions are pothole
   patches and traffic marshals that treat symptoms only.

Your job, for the item under review (`subject`):
- Explain step by step, from specific evidence fields, what the root cause is (or, for a hypothesis, whether the
  evidence supports inspecting it next), where it sits, where and when the problem started and how it spread.
- Say whether you agree with the system (the field confirmation for a confirmed item, or the tracer's ranking for a
  hypothesis). Name competing explanations, including background noise and other candidates.
- Assess the departments' policy: did crews go to the cause quickly, or waste work on symptoms or healthy assets?
- Recommend concrete actions with an owning department or unit.
- List caveats (simulated city, noisy reporting, under-reporting wards, onset estimate, single confirmation).
Calibrate confidence: "high" only for a field-confirmed item whose zone, mechanism and symptom chain agree; a
hypothesis is at most "medium". Quote numbers exactly as they appear in the evidence. Never introduce numbers that
are not in the evidence."""


def load_key() -> str | None:
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    here = Path(__file__).resolve()
    for env in (here.parents[3] / ".env", here.parents[2] / ".env"):  # SmartCity/.env, Project/.env
        if env.is_file():
            for line in env.read_text().splitlines():
                if line.strip().startswith("GROQ_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


POLICY_DESCRIPTION = {
    "rl": "reinforcement-learning dispatch policy (Double DQN trained offline in this simulator) choosing among the tracer's candidates",
    "tracer": "deterministic baseline: repair what an inspection confirmed, else inspect the top-scoring candidate",
    "complaint_count": "status-quo baseline: repair whatever has the most complaints on its own block, never inspects",
    "random": "random choice among candidates (sanity baseline)",
}


def build_evidence(cfg, report: dict[str, Any], subject: dict[str, Any], work: list[dict[str, Any]],
                   metrics: dict[str, Any], policy: str) -> dict[str, Any]:
    """Public evidence for one confirmed root cause or hypothesis. Never includes ground truth."""
    layer = cfg.layer(subject["where"]["layer"] if "where" in subject else subject["layer"])
    mech = {l.id: {"department": l.department, "asset": l.label, "can_cause": sorted(l.match), "primary": l.primary,
                   "inspection": l.inspect_label, "inspection_miss_prob": l.inspect_miss_prob}
            for l in cfg.layers if l.id in cfg.root_cause_layers()}
    item = {k: v for k, v in subject.items() if k not in ("p", "fixed", "tip", "evidence_ids", "simulated")}
    others = [{"asset": h["asset_name"], "score": h["score"], "coverage": h["coverage"], "lift": h["lift"],
               "root_first": h["root_first"]} for h in report.get("hypotheses", [])]
    confirmed = [{"asset": r["where"]["asset"], "status": r["status"]} for r in report.get("root_causes", [])]
    return {
        "subject_kind": "hypothesis" if subject.get("status") == "HYPOTHESIS" else "confirmed_root_cause",
        "subject": item,
        "layer_mechanism": layer.mechanism,
        "mechanism_table": mech,
        "other_hypotheses": others,
        "other_confirmed": [c for c in confirmed if c["asset"] != item.get("where", {}).get("asset")],
        "work_log_for_this_layer": work[-12:],
        "episode_so_far": {k: metrics.get(k) for k in ("complaints", "inspections", "repairs", "false_repairs", "symptom_actions")},
        "policy": f"{policy}: {POLICY_DESCRIPTION.get(policy, policy)}",
        "clock": report.get("clock"),
        "tick_hours": cfg.tick_hours,
    }


NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?\s?%?")
DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-"})


def ungrounded_numbers(analysis: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    """Numbers in the answer that do not appear in the evidence (rounding-level tolerance). Same rule as city_sim."""
    have = [abs(float(t.rstrip("% "))) for t in NUM.findall(json.dumps(evidence, ensure_ascii=False).translate(DASHES))]
    text = json.dumps({k: v for k, v in analysis.items() if k not in ("confidence", "agrees_with_system")},
                      ensure_ascii=False).translate(DASHES)
    bad = []
    for raw in NUM.findall(text):
        tok = raw.replace(" ", "")
        pct = tok.endswith("%")
        v = abs(float(tok.rstrip("%")))
        if v <= 10 and float(v).is_integer() and not pct:
            continue                                     # ward / block / list indices, small counts
        cands = [v, v / 100] if pct else [v]
        decimals = len(tok.rstrip("%").split(".")[1]) if "." in tok else 0
        unit = 0.5 * 10 ** (-decimals)
        if not any(abs(c - h) <= max(unit, abs(h) * 0.02) for c in cands for h in have):
            bad.append(tok)
    return sorted(set(bad))


def deterministic_summary(subject: dict[str, Any]) -> dict[str, Any]:
    hyp = subject.get("status") == "HYPOTHESIS"
    name = subject["asset_name"] if hyp else subject["where"]["asset"]
    return {
        "headline": f"{'Hypothesis' if hyp else 'Confirmed root cause'}: {name}",
        "root_cause": "No LLM was reachable; this is the system's own record.",
        "where_it_started": "" if hyp else str((subject.get("started") or {}).get("estimated", "")),
        "mechanism": subject.get("why_if_true") if hyp else subject.get("why", ""),
        "agrees_with_system": True,
        "system_comment": "No independent review was possible.",
        "reasoning_steps": [], "alternatives_considered": [], "policy_assessment": "",
        "recommended_actions": [{"action": subject.get("next_step", "") if hyp else "monitor complaints in the zone",
                                 "owner": subject.get("department") or subject.get("responsible_department", ""), "expected_effect": ""}],
        "caveats": ["LLM unavailable"], "confidence": "low",
    }


async def root_cause(client: httpx.AsyncClient, rc_cfg, local_url: str, local_model: str,
                     evidence: dict[str, Any], subject: dict[str, Any]) -> dict[str, Any]:
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "Evidence (JSON):\n" + json.dumps(evidence, separators=(",", ":"))}]
    key = load_key()
    attempts: list[dict[str, Any]] = []
    for model in (rc_cfg.model, rc_cfg.fallback_model):
        if not key:
            attempts.append({"model": model, "error": "GROQ_API_KEY not set"})
            break
        t0 = time.perf_counter()
        try:
            res = await client.post(
                f"{rc_cfg.base_url}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": messages, "temperature": rc_cfg.temperature,
                      "reasoning_effort": rc_cfg.reasoning_effort, "max_completion_tokens": rc_cfg.max_tokens,
                      "response_format": {"type": "json_schema", "json_schema": {"name": "civic_root_cause", "strict": True, "schema": SCHEMA}}},
                timeout=rc_cfg.timeout_sec)
            body = res.json()
            if res.status_code != 200:
                raise RuntimeError(str(body.get("error", body))[:300])
            msg = body["choices"][0]["message"]
            analysis = json.loads(msg["content"])
            return {"analysis": analysis, "provider": "groq", "model": model, "reasoning_trace": msg.get("reasoning"),
                    "usage": body.get("usage"), "latency_ms": round((time.perf_counter() - t0) * 1000),
                    "ungrounded_numbers": ungrounded_numbers(analysis, evidence), "attempts": attempts, "evidence_sent": evidence}
        except Exception as exc:
            attempts.append({"model": model, "error": f"{type(exc).__name__}: {exc}"[:300]})

    small = {**evidence, "work_log_for_this_layer": evidence["work_log_for_this_layer"][-4:], "mechanism_table": None}
    t0 = time.perf_counter()
    try:
        res = await client.post(
            f"{local_url}/chat/completions",
            json={"model": local_model, "temperature": 0.2, "max_tokens": 900,
                  "messages": [messages[0], {"role": "user", "content": "Evidence (JSON):\n" + json.dumps(small, separators=(",", ":"))}],
                  "response_format": {"type": "json_schema", "json_schema": {"name": "civic_root_cause", "schema": SCHEMA}}},
            timeout=rc_cfg.timeout_sec)
        analysis = json.loads(res.json()["choices"][0]["message"]["content"])
        return {"analysis": analysis, "provider": "local", "model": local_model, "reasoning_trace": None,
                "usage": res.json().get("usage"), "latency_ms": round((time.perf_counter() - t0) * 1000),
                "ungrounded_numbers": ungrounded_numbers(analysis, small), "attempts": attempts, "evidence_sent": small}
    except Exception as exc:
        attempts.append({"model": local_model, "error": f"{type(exc).__name__}: {exc}"[:300]})
    return {"analysis": deterministic_summary(subject), "provider": "none", "model": None, "reasoning_trace": None,
            "usage": None, "latency_ms": None, "ungrounded_numbers": [], "attempts": attempts, "evidence_sent": evidence}


# ---------------------------------------------------------------- crew decision explanations (local Gemma)
GNUM = re.compile(r"-?\d+(?:\.\d+)?")
EXPLAIN_SYSTEM = (
    "You explain one decision made by a city department's dispatch policy in a SIMULATED city to an operator. Each "
    "tick the department picks one candidate: inspect an asset, repair it, or wait. Candidate features: coverage = "
    "share of matching complaints inside the asset's zone, lift = complaint density there vs the city average, "
    "root_first = its own area reported first, insp_pos/insp_neg = an earlier inspection found / did not find a fault, "
    "q = the policy's estimated value of the action (only for the RL policy; higher is preferred). Use at most 3 "
    "sentences, plain language. Say why this candidate beat the alternatives and what the crew found. Do not state any "
    "number that is not in the record. The policy 'rl' is a reinforcement-learning dispatch policy, 'tracer' a "
    "deterministic ranking rule.")


def grounded(text: str, source: str) -> bool:
    have = [float(x) for x in GNUM.findall(source)]
    return all(any(abs(float(t) - h) <= max(0.051, abs(h) * 0.01) for h in have) for t in GNUM.findall(text))


def deterministic_explanation(rec: dict[str, Any]) -> str:
    c = rec["chosen"]
    if c["action"] == "wait":
        return f"The {rec['department']} department waited: no candidate looked worth a crew this tick."
    f = c["features"]
    alt = rec["alternatives"][0] if rec["alternatives"] else None
    why = (f"its zone holds {f.get('cov_primary', 0):.0%} of matching recent complaints with lift {f.get('lift', 0):.2f}"
           if f else "it ranked highest")
    out = f"The {rec['department']} crew chose to {c['action']} {c['asset_name']} because {why}."
    if alt:
        out += f" The next option was to {alt['action']} {alt['asset_name']}."
    out += " The crew found the fault." if rec["found_fault"] else " The crew found nothing wrong."
    return out


async def explain_action(client: httpx.AsyncClient, local_url: str, local_model: str, timeout: float, rec: dict[str, Any]) -> dict[str, Any]:
    source = json.dumps(rec, separators=(",", ":"))
    fallback = deterministic_explanation(rec)
    try:
        res = await client.post(f"{local_url}/chat/completions", timeout=timeout, json={
            "model": local_model, "temperature": 0.2, "max_tokens": 200,
            "messages": [{"role": "system", "content": EXPLAIN_SYSTEM}, {"role": "user", "content": f"Decision record: {source}"}]})
        res.raise_for_status()
        text = res.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return {"explanation": fallback, "llm_text": None, "grounded": None, "model": None,
                "note": f"LLM unavailable ({type(exc).__name__}); deterministic explanation shown."}
    ok = grounded(text, source)
    return {"explanation": text if ok else fallback, "llm_text": text, "grounded": ok, "model": local_model,
            "note": None if ok else "The LLM mentioned numbers absent from the record; showing the deterministic explanation."}
