"""Population agent graph: LLM path, invalid-output fallback, LLM-down fallback, trip arithmetic, grounding."""

import asyncio
import json
import random
from pathlib import Path

import pytest

from app.agents import build_graph, clock, fallback_plan, make_trips, Plan
from app.config import ClusterConfig, load_config

CFG = load_config(Path(__file__).resolve().parent.parent / "config.yaml")
CLUSTER = ClusterConfig(id="t1", name="Test office workers", persona="office workers", population=900, source_id=0)


def obs(jammed=(), speed=90):
    return {
        "clock": "07:40", "sim_time": 600, "episode": 0, "plan_id": "P1-test",
        "route": {"route": "corridor", "jammed_links": list(jammed), "mean_speed_pct": speed,
                  "entry_backlog_veh": 0, "disruption_active": False},
    }


def run_graph(llm_reply):
    posted = []

    async def llm(_messages):
        if isinstance(llm_reply, Exception):
            raise llm_reply
        return llm_reply

    async def post(trips):
        posted.extend(trips)
        return {"trip_ids": list(range(len(trips)))}

    graph = build_graph(CFG, llm, post, random.Random(0))
    out = asyncio.run(graph.ainvoke({"cluster": CLUSTER.model_dump(), "observation": obs(), "memory": [], "steps": []}))
    return out, posted


def test_llm_plan_is_used_and_trips_posted():
    out, posted = run_graph(json.dumps({"intent": "commute", "departure": "now", "share": "high", "reason": "late"}))
    assert out["decided_by"] == "llm"
    assert [s["node"] for s in out["steps"]] == ["observe", "decide", "validate", "dispatch"]
    assert posted and all(t["vehicles"] <= CFG.car_cluster_size for t in posted)


def test_invalid_llm_output_falls_back():
    out, posted = run_graph(json.dumps({"intent": "teleport", "departure": "now", "share": "high", "reason": "x"}))
    assert out["decided_by"] == "rule_fallback"
    assert "fallback" in [s["node"] for s in out["steps"]]
    assert posted


def test_llm_down_falls_back():
    out, _ = run_graph(ConnectionError("llama-server down"))
    assert out["decided_by"] == "rule_fallback"
    assert out["steps"][1]["error"].startswith("ConnectionError")


def test_trip_arithmetic_is_deterministic_from_config():
    plan = Plan(intent="commute", departure="now", share="medium", reason="r")
    trips = make_trips(plan, CLUSTER, CFG, random.Random(1), "P")
    expected = CLUSTER.population * CFG.share_fraction["medium"] * CFG.car_ratio["commute"]
    assert sum(t["vehicles"] for t in trips) == pytest.approx(expected, abs=0.05)
    lo, hi = CFG.departure_window_sec["now"]
    assert all(lo <= t["depart_in_sec"] <= hi for t in trips)
    assert make_trips(Plan(intent="stay_home", departure="now", share="high", reason="r"), CLUSTER, CFG, random.Random(1), "P") == []


def test_fallback_avoids_jams():
    assert fallback_plan(obs(jammed=["link J1→J2"]), CLUSTER).departure == "delay_short"
    assert fallback_plan(obs(), CLUSTER).departure == "now"


def test_clock():
    assert clock(0, "07:30") == "07:30"
    assert clock(1799, "07:30") == "07:59"


def test_grounding_rejects_invented_numbers():
    from app.server import grounded
    src = json.dumps({"q": [-2.03, -1.98], "junction_label": "J5", "epsilon": 0.7})
    assert grounded("At J5 Q(switch) -1.98 beat -2.03 with epsilon 0.7.", src)
    assert not grounded("This will cut delay by 35%.", src)
