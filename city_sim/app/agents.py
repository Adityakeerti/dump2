"""LangGraph people-cluster agent: observe -> decide (Gemma) -> validate -> [fallback] -> dispatch.

The LLM only picks categorical options (intent, departure, share) plus a short reason. Vehicle counts and
departure times are computed deterministically from config tables, so the twin never receives numbers that
a language model made up. If the LLM is unreachable or returns an invalid plan, a transparent rule-based
fallback decides instead and the trace says so.
"""

from __future__ import annotations

import json
import math
import random
import time
from typing import Any, Awaitable, Callable, TypedDict

import httpx
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import DEPARTURES, INTENTS, SHARES, ClusterConfig, Departure, Intent, Share, SimConfig


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    departure: Departure
    share: Share
    reason: str = Field(max_length=240)


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "departure": {"type": "string", "enum": list(DEPARTURES)},
        "share": {"type": "string", "enum": list(SHARES)},
        "reason": {"type": "string", "maxLength": 200},
    },
    "required": ["intent", "departure", "share", "reason"],
}


class AgentState(TypedDict, total=False):
    cluster: dict[str, Any]
    observation: dict[str, Any]
    memory: list[dict[str, Any]]
    prompt: list[dict[str, str]]
    raw: str | None
    plan: dict[str, Any] | None
    decided_by: str
    error: str | None
    trips: list[dict[str, Any]]
    steps: list[dict[str, Any]]


def clock(sim_time: float, start: str) -> str:
    h, m = (int(x) for x in start.split(":"))
    total = h * 60 + m + int(sim_time // 60)
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


def route_conditions(cluster: ClusterConfig, state: dict[str, Any], topo: dict[str, Any]) -> dict[str, Any]:
    """Summarise what this cluster would experience on its route, from the twin's live state."""
    links = state.get("links", [])
    src = next((s for s in topo["geometry"]["sources"] if s["id"] == cluster.source_id), None)
    backlog = float(state.get("source_backlog", {}).get(str(cluster.source_id), 0.0))
    if src is None or src["kind"] == "arterial":
        jammed = [l["name"] for l in links if l["jammed"]]
        speed = sum(l["mean_speed_ratio"] for l in links) / max(len(links), 1)
        route = "the full arterial corridor"
    else:
        j = src["junction"]
        jn = next((x for x in state.get("junctions", []) if x["id"] == j), {})
        jammed = [l["name"] for l in links if l["jammed"] and l["id"] in (j, j + 1)]
        speed = sum(l["mean_speed_ratio"] for l in links if l["id"] in (j, j + 1)) / 2
        route = f"cross street into junction J{j + 1} (cross queue {jn.get('cross_queue', 0):.1f} veh)"
    return {
        "route": route,
        "jammed_links": jammed,
        "mean_speed_pct": round(100 * speed),
        "entry_backlog_veh": round(backlog, 1),
        "disruption_active": bool(state.get("disruptions")),
    }


def fallback_plan(obs: dict[str, Any], cluster: ClusterConfig) -> Plan:
    """Transparent rule: avoid departing into a jam; otherwise commute now at medium share."""
    congested = obs["route"]["jammed_links"] or obs["route"]["mean_speed_pct"] < 60
    if congested:
        return Plan(intent="commute", departure="delay_short", share="low", reason="rule: route congested, delay")
    return Plan(intent="commute", departure="now", share="medium", reason="rule: route clear, travel now")


def make_trips(plan: Plan, cluster: ClusterConfig, cfg: SimConfig, rng: random.Random, plan_id: str) -> list[dict[str, Any]]:
    vehicles = cluster.population * cfg.share_fraction[plan.share] * cfg.car_ratio[plan.intent]
    if vehicles <= 0:
        return []
    n = max(1, math.ceil(vehicles / cfg.car_cluster_size))
    lo, hi = cfg.departure_window_sec[plan.departure]
    return [
        {
            "cluster_id": cluster.id,
            "cluster_name": cluster.name,
            "intent": plan.intent,
            "plan_id": plan_id,
            "source_id": cluster.source_id,
            "vehicles": round(vehicles / n, 2),
            "depart_in_sec": round(rng.uniform(lo, hi), 1),
        }
        for _ in range(n)
    ]


LlmCall = Callable[[list[dict[str, str]]], Awaitable[str]]


def make_llm(cfg: SimConfig, client: httpx.AsyncClient) -> LlmCall:
    async def call(messages: list[dict[str, str]]) -> str:
        res = await client.post(
            f"{cfg.llm_base_url}/chat/completions",
            json={
                "model": cfg.llm_model,
                "messages": messages,
                "temperature": cfg.llm_temperature,
                "max_tokens": cfg.llm_max_tokens,
                "response_format": {"type": "json_schema", "json_schema": {"name": "plan", "schema": PLAN_SCHEMA}},
            },
            timeout=cfg.llm_timeout_sec,
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]

    return call


def build_graph(cfg: SimConfig, llm: LlmCall, post_trips: Callable[[list[dict[str, Any]]], Awaitable[Any]], rng: random.Random):
    def step(state: AgentState, node: str, t0: float, **info: Any) -> list[dict[str, Any]]:
        return state.get("steps", []) + [{"node": node, "ms": round((time.perf_counter() - t0) * 1000, 1), **info}]

    async def observe(state: AgentState) -> AgentState:
        t0 = time.perf_counter()
        c = state["cluster"]
        obs = state["observation"]
        mem = state.get("memory", [])
        history = "; ".join(
            f"at {m['clock']} you chose {m['intent']}/{m['departure']}/{m['share']}"
            + (f", your cars averaged {m['mean_delay_sec']:.0f}s delay" if m.get("mean_delay_sec") is not None else "")
            for m in mem
        ) or "no previous trips this session"
        r = obs["route"]
        system = (
            f"You plan travel for a cluster of {c['population']} people: {c['persona']}. "
            "Choose what the cluster does in the next few minutes. intent: commute, errand, leisure or stay_home. "
            "departure: now, delay_short (2-4 min) or delay_long (5-10 min). share: low, medium or high fraction "
            "of the cluster that travels. Give a short reason. Reply with JSON only."
        )
        user = (
            f"Time {obs['clock']}. Your route: {r['route']}. Average speed {r['mean_speed_pct']}% of free flow. "
            f"Jammed links: {', '.join(r['jammed_links']) or 'none'}. Vehicles waiting to enter at your entry: "
            f"{r['entry_backlog_veh']}. Lane closure or disruption active: {'yes' if r['disruption_active'] else 'no'}. "
            f"Your recent history: {history}."
        )
        prompt = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return {"prompt": prompt, "steps": step(state, "observe", t0, summary=user)}

    async def decide(state: AgentState) -> AgentState:
        t0 = time.perf_counter()
        try:
            raw = await llm(state["prompt"])
            return {"raw": raw, "error": None, "steps": step(state, "decide", t0, model=cfg.llm_model, raw=raw)}
        except Exception as exc:  # network, timeout, server error
            err = f"{type(exc).__name__}: {exc}"[:200]
            return {"raw": None, "error": err, "steps": step(state, "decide", t0, model=cfg.llm_model, error=err)}

    async def validate(state: AgentState) -> AgentState:
        t0 = time.perf_counter()
        if state.get("raw") is None:
            return {"plan": None, "steps": step(state, "validate", t0, ok=False, error="no LLM output")}
        try:
            plan = Plan.model_validate(json.loads(state["raw"]))
            return {"plan": plan.model_dump(), "decided_by": "llm", "steps": step(state, "validate", t0, ok=True)}
        except (ValidationError, json.JSONDecodeError) as exc:
            err = str(exc)[:200]
            return {"plan": None, "error": err, "steps": step(state, "validate", t0, ok=False, error=err)}

    async def fallback(state: AgentState) -> AgentState:
        t0 = time.perf_counter()
        cl = ClusterConfig.model_validate(state["cluster"])
        plan = fallback_plan(state["observation"], cl)
        return {"plan": plan.model_dump(), "decided_by": "rule_fallback", "steps": step(state, "fallback", t0, plan=plan.model_dump())}

    async def dispatch(state: AgentState) -> AgentState:
        t0 = time.perf_counter()
        cl = ClusterConfig.model_validate(state["cluster"])
        plan = Plan.model_validate(state["plan"])
        trips = make_trips(plan, cl, cfg, rng, state["observation"]["plan_id"])
        posted = None
        if trips:
            try:
                posted = await post_trips(trips)
            except Exception as exc:
                return {"trips": [], "steps": step(state, "dispatch", t0, error=f"{type(exc).__name__}: {exc}"[:200])}
        veh = round(sum(t["vehicles"] for t in trips), 1)
        return {"trips": trips, "steps": step(state, "dispatch", t0, car_clusters=len(trips), vehicles=veh, twin=posted)}

    g = StateGraph(AgentState)
    g.add_node("observe", observe)
    g.add_node("decide", decide)
    g.add_node("validate", validate)
    g.add_node("fallback", fallback)
    g.add_node("dispatch", dispatch)
    g.set_entry_point("observe")
    g.add_edge("observe", "decide")
    g.add_edge("decide", "validate")
    g.add_conditional_edges("validate", lambda s: "dispatch" if s.get("plan") else "fallback", {"dispatch": "dispatch", "fallback": "fallback"})
    g.add_edge("fallback", "dispatch")
    g.add_edge("dispatch", END)
    return g.compile()
