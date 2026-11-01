"""Root-cause LLM bridge: no ground-truth leakage, number grounding, fallback chain."""

import asyncio
import json

import httpx

from app import root_cause

DIAG = {
    "found": True, "cell": 29, "sim_time": 560.0, "policy": "fixed-time",
    "jam": {"tail_cell": 19, "head_cell": 31, "cell_count": 13, "start_time_sec": 205.0, "end_time_sec": 560.0,
            "extent_m": 180.0, "duration_sec": 355.0, "mean_speed_mps": 2.1, "cells": list(range(19, 32))},
    "origin": {"cell": 31, "earliest_onset_sec": 205.0, "wave_speed_mps": 5.56, "theoretical_wave_speed_mps": 5.56,
               "method": "m", "evidence_trail": [{"cell_id": 31, "timestamp_sec": 205.0, "mean_speed_mps": 2.0,
                                                  "mean_flow_vps": 0.3, "is_discharge_origin": True, "description": "Deploy road maintenance"}]},
    "capacity_at_origin": {"cell_id": 31, "capacity_ratio": 0.25, "estimated_capacity": 0.12, "nominal_capacity": 0.5,
                           "confidence_interval": [0.2, 0.3], "change_points": [205.0], "significant_drop_detected": True, "time_window_sec": [205, 560]},
    "counterfactual": {"scenario_name": "downstream_spillback", "rungs": [{"rung_name": "restore_capacity", "mean_recovery_vhr": 1.15,
                       "ci_lower_vhr": 1.08, "ci_upper_vhr": 1.21, "rank": 1}], "signal_alternatives": [], "noise_floor_vhr": 0.01},
    "situation": {"top_hypothesis": {"hypothesis_type": "recurring_capacity_drop", "recommended_action": "a", "responsible_party": "p"},
                  "ranked_hypotheses": [{"hypothesis_type": "recurring_capacity_drop", "target_cell": 31, "vehicle_hours_recovered": 1.15,
                                         "ci_lower": 1.08, "ci_upper": 1.21, "confidence_score": 0.6, "recommended_action": "a", "responsible_party": "p"}]},
    "rl_evidence": [{"junction": "J4", "recent_decisions": [{"id": 1, "t": 500, "text": "x"}] * 5}],
    "validation": {"scenario": "downstream_spillback", "planted_windows": [{"cells": [30]}]},
}


def test_evidence_has_no_ground_truth_or_scenario_name():
    ev = json.dumps(root_cause.compact_evidence(DIAG, None))
    assert "spillback" not in ev and "validation" not in ev and "planted" not in ev
    assert "Deploy road maintenance" not in ev  # repo template strings are not evidence


def test_ungrounded_numbers_flagged():
    ev = root_cause.compact_evidence(DIAG, None)
    ok = {"headline": "Capacity at cell 31 fell to 25% (0.12 of 0.5 vps); restore recovers 1.15 [1.08‑1.21]"}
    bad = {"headline": "This cuts delay by 63% and saves 42.7 hours"}
    assert root_cause.ungrounded_numbers(ok, ev) == []
    assert set(root_cause.ungrounded_numbers(bad, ev)) == {"63%", "42.7"}
    # unicode minus / non-breaking-hyphen ranges and the 95 % confidence level are not false positives
    tricky = {"headline": "CI 1.08\u20111.21 at the 95 % level; speed \u22122.0 m/s"}
    assert root_cause.ungrounded_numbers(tricky, ev) == []


def test_falls_back_to_deterministic_summary_when_no_llm(monkeypatch):
    monkeypatch.setattr(root_cause, "_load_key", lambda: None)

    def handler(request):
        return httpx.Response(503)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            cfg = {"base_url": "http://groq.invalid", "model": "m1", "fallback_model": "m2", "reasoning_effort": "medium",
                   "temperature": 0.2, "max_tokens": 100, "timeout_sec": 5}
            return await root_cause.reason(client, DIAG, None, cfg, "http://local.invalid/v1", "gemma")

    out = asyncio.run(run())
    assert out["provider"] == "none"
    assert out["analysis"]["confidence"] == "low"
    assert [a["model"] for a in out["attempts"]] == ["m1", "gemma"]
