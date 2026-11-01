"""LLM reasoning guardrails: no ground truth in the evidence, number grounding, fallback chain."""

import asyncio
import json

import httpx
import pytest

from app import reasoning
from app.config import load_config
from app.diagnosis import root_cause_reports
from app.env import CivicEnv
from app.policies import make_tracer_policy

CFG = load_config()


def episode(scenario):
    env = CivicEnv(CFG)
    pol = make_tracer_policy(CFG)
    obs = env.reset(seed=21, scenario=scenario)
    while not env.done:
        obs, *_ = env.step({d: pol(obs[d]) for d in env.departments}, policy="tracer")
    return env, root_cause_reports(CFG, env.city, env.portal, env.tick)


def evidence_for(env, report, subject):
    return reasoning.build_evidence(CFG, report, subject, [], env.episode_metrics(), "tracer")


def test_evidence_never_contains_ground_truth():
    env, report = episode(["sewer_blockage"])
    subjects = report["root_causes"] + report["hypotheses"]
    assert subjects
    for s in subjects:
        blob = json.dumps(evidence_for(env, report, s))
        for leak in ("sewer_blockage", "onset_tick", "identified_tick", "cause_type", "ground_truth"):
            assert leak not in blob


def test_ungrounded_numbers_flags_invented_values_only():
    ev = {"affected": {"complaints": 137, "lift": 3.42}, "coverage": 0.61}
    ok = {"headline": "137 complaints, lift 3.4, coverage 61%", "confidence": "high"}
    bad = {"headline": "about 250 complaints and lift 7.9"}
    assert reasoning.ungrounded_numbers(ok, ev) == []
    assert reasoning.ungrounded_numbers(bad, ev) == ["250", "7.9"]


def test_root_cause_falls_back_to_deterministic_when_no_llm(monkeypatch):
    monkeypatch.setattr(reasoning, "load_key", lambda: None)
    env, report = episode(["water_main_leak"])
    subject = (report["root_causes"] or report["hypotheses"])[0]

    async def go():
        async with httpx.AsyncClient() as client:
            return await reasoning.root_cause(client, CFG.live.root_cause, "http://127.0.0.1:1/v1", "none",
                                              evidence_for(env, report, subject), subject)
    out = asyncio.run(go())
    assert out["provider"] == "none" and out["analysis"]["confidence"] == "low"
    assert [a["error"] for a in out["attempts"]][0] == "GROQ_API_KEY not set"


@pytest.mark.parametrize("llm_text,expect_grounded", [
    ("The crew inspected the feeder because most streetlight complaints sat in its zone.", True),
    ("The crew inspected the feeder because 83 complaints sat in its zone.", False),
])
def test_explanation_grounding(monkeypatch, llm_text, expect_grounded):
    rec = {"department": "municipal", "policy": "rl", "found_fault": True, "alternatives": [],
           "chosen": {"action": "inspect", "asset_name": "Streetlight feeder circuit 2", "layer": "streetlight",
                      "features": {"cov_primary": 0.7, "lift": 1.9}, "q": 2.31}}

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": llm_text}}]})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await reasoning.explain_action(client, "http://llm/v1", "gemma", 5, rec)
    out = asyncio.run(go())
    assert out["grounded"] is expect_grounded
    assert out["explanation"] == (llm_text if expect_grounded else reasoning.deterministic_explanation(rec))
