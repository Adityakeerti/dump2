"""Civic simulator service: the city runs live, residents complain, departments act with the trained policy.

Run: uvicorn app.server:app --port 8005   (from civic_sim/, SmartCity venv)
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import os
from collections import deque
from typing import Any

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import reasoning
from app.agents import build_citizen_graph, make_llm
from app.config import BASE, POLICIES, load_config
from app.diagnosis import root_cause_reports
from app.dqn import CandidateDQN
from app.env import CivicEnv
from app.policies import build_policy
from app.tracer import feature_names, max_candidates
from app.world import geometry

cfg = load_config(os.environ.get("CIVIC_SIM_CONFIG"))
LLM_URL = os.environ.get("LLM_BASE_URL", cfg.live.llm_base_url)
PORTAL_URL = os.environ.get("COMPLAINT_SERVICE_URL", cfg.live.portal_bridge.url)
cfg = cfg.model_copy(update={"live": cfg.live.model_copy(update={"llm_base_url": LLM_URL})})


class Runtime:
    def __init__(self) -> None:
        self.env = CivicEnv(cfg)
        self.agent: CandidateDQN | None = None
        self.agent_meta: dict | None = None
        self.policy_name = cfg.live.policy
        self.running = True
        self.seeds = itertools.count(cfg.evaluation.seed_offset * 2)
        self.scenario: list[str] | None = None
        self.policies: dict = {}
        self.actions: deque[dict] = deque(maxlen=cfg.live.log_size)
        self.traces: deque[dict] = deque(maxlen=cfg.live.log_size)
        self.last_episode: dict | None = None
        self.client: httpx.AsyncClient | None = None
        self.graph = None
        self.llm_ok: bool | None = None
        self.bridge_sent = 0
        self.last_error: str | None = None
        self.lock = asyncio.Lock()
        self.tick_interval = cfg.live.tick_interval_sec
        self.decisions: dict[str, dict] = {}          # action id -> what the policy saw (for explanations)
        self.reasoning_cache: dict[tuple, dict] = {}


rt = Runtime()


def load_agent() -> None:
    path = BASE / cfg.rl.checkpoint_path
    if path.is_file():
        agent = CandidateDQN(cfg.rl, len(feature_names(cfg)), max_candidates(cfg), cfg.seed)
        rt.agent_meta = agent.load(path)
        rt.agent = agent


def effective_policy() -> str:
    return "tracer" if rt.policy_name == "rl" and rt.agent is None else rt.policy_name


def reset(seed: int | None = None, scenario: list[str] | None = None) -> None:
    seed = next(rt.seeds) if seed is None else seed
    rt.scenario = scenario
    rt.env.reset(seed=seed, scenario=scenario)
    rt.policies = {d: build_policy(effective_policy(), cfg, rt.agent, seed + i) for i, d in enumerate(rt.env.departments)}
    rt.actions.clear()


async def rewrite_texts(env: CivicEnv) -> None:
    """Citizen agents rewrite a few of this tick's complaints in their own words (LLM), rest keep templates."""
    new = [c for c in env.portal.complaints if c.tick == env.tick][: cfg.live.llm_max_per_tick]
    if not new or rt.graph is None:
        return

    async def one(c) -> None:
        desc = env.population.describe(c.citizen, env.city)
        cat = cfg.categories[c.category]
        out = await rt.graph.ainvoke({"citizen": desc, "incident": {"label": cat.label, "template": c.text}, "steps": []})
        if out.get("written_by") == "llm":
            c.text = f"{out['text']['title']}: {out['text']['description']}"
            c.text_by = "llm"
        rt.llm_ok = out.get("written_by") == "llm"
        rt.traces.append({"complaint": c.id, "citizen": desc, "written_by": out.get("written_by"), "steps": out.get("steps")})

    await asyncio.gather(*(one(c) for c in new), return_exceptions=True)


async def bridge(env: CivicEnv) -> None:
    """Forward a few complaints to the main complaint portal (complaint_module): its intake agent, guardrail and
    worker dispatch run on them as on any citizen complaint."""
    b = cfg.live.portal_bridge
    if not b.enabled or b.max_per_tick == 0:
        return
    for c in [c for c in env.portal.complaints if c.tick == env.tick][: b.max_per_tick]:
        cat = cfg.categories[c.category]
        if cat.department != "municipal":
            continue                                     # complaint_module only covers municipal departments
        try:
            res = await rt.client.post(f"{PORTAL_URL}/api/complaints", data={
                "title": cat.label, "description": c.text, "category": cat.id,
                "address": f"{env.city.block_name(c.block)}, Ward {int(env.city.ward[c.block]) + 1} (SIMULATED)",
                "lat": float(env.city.lat[c.block]), "lng": float(env.city.lon[c.block])}, timeout=20)
            res.raise_for_status()
            rt.bridge_sent += 1
        except Exception as exc:
            rt.last_error = f"bridge: {type(exc).__name__}: {exc}"[:200]


EXPLAIN_FEATURES = ("cov_primary", "cov_secondary", "lift", "root_first", "zone_frac", "insp_pos", "insp_neg",
                    "repaired_recent", "repair_failed", "score")


def decision_record(obs, choice: int) -> dict:
    """What the department's policy saw when it chose: the chosen candidate, its features, and the best alternatives."""
    pol = effective_policy()
    q = rt.agent.q(obs.feats, obs.mask) if pol == "rl" and rt.agent is not None else None
    city = rt.env.city

    def cand(i: int) -> dict:
        c = obs.candidates[i]
        name = None if c.layer is None else city.layers[c.layer].assets[c.asset].name
        out = {"action": c.action, "asset_name": name, "layer": c.layer,
               "features": {k: round(float(c.features[k]), 3) for k in EXPLAIN_FEATURES if k in c.features}}
        if q is not None:
            out["q"] = round(float(q[i]), 3)
        return out

    rank = sorted((i for i in range(len(obs.candidates)) if i != choice),
                  key=lambda i: -(q[i] if q is not None else obs.candidates[i].features.get("score", 0.0)))
    return {"department": obs.department, "policy": pol, "chosen": cand(choice),
            "alternatives": [cand(i) for i in rank[:3]], "candidates_considered": len(obs.candidates)}


async def tick_once() -> dict:
    async with rt.lock:
        env = rt.env
        if env.done:
            rt.last_episode = {"seed": env.seed, "metrics": env.episode_metrics(), "ground_truth": env.ground_truth(),
                               "diagnosis": root_cause_reports(cfg, env.city, env.portal, env.tick)}
            reset()
        obs = env.obs
        choices = {d: rt.policies[d](obs[d]) for d in env.departments}
        records = {d: decision_record(obs[d], choices[d]) for d in env.departments}
        _, reward, _, info = env.step(choices, policy=effective_policy())
        for a in info["actions"]:
            if a.get("block") is not None:
                a["block"] = env.city.block_name(a["block"])
            aid = f"{env.seed}-{env.tick - 1}-{a['department']}"
            rt.actions.append({"id": aid, "tick": env.tick - 1, "clock": cfg.clock(env.tick - 1), **a})
            rt.decisions[aid] = {**records[a["department"]], "clock": cfg.clock(env.tick - 1), "found_fault": a["found_fault"]}
        if len(rt.decisions) > cfg.live.log_size:
            for k in list(rt.decisions)[: len(rt.decisions) - cfg.live.log_size]:
                del rt.decisions[k]
    await asyncio.gather(rewrite_texts(env), bridge(env))
    return {"tick": env.tick, "reward": round(reward, 3), **info}


async def loop() -> None:
    while True:
        await asyncio.sleep(rt.tick_interval)
        if rt.running:
            try:
                await tick_once()
            except Exception as exc:                     # keep the city running; surface the error in /health
                rt.last_error = f"{type(exc).__name__}: {exc}"[:200]


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    rt.client = httpx.AsyncClient()
    rt.graph = build_citizen_graph(make_llm(cfg, rt.client))
    load_agent()
    reset()
    task = asyncio.create_task(loop())
    yield
    task.cancel()
    await rt.client.aclose()


app = FastAPI(title="CitySense civic simulator", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def complaint_json(c, env: CivicEnv) -> dict:
    cat = cfg.categories[c.category]
    return {"id": c.id, "tick": c.tick, "clock": cfg.clock(c.tick), "category": cat.id, "label": cat.label,
            "department": c.department, "unit": c.unit, "block": env.city.block_name(c.block),
            "ward": int(env.city.ward[c.block]) + 1, "lat": float(env.city.lat[c.block]), "lon": float(env.city.lon[c.block]),
            "text": c.text, "text_by": c.text_by, "status": c.status,
            "citizen": env.population.describe(c.citizen, env.city)}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Live view of the simulated city (polls the JSON API below)."""
    return FileResponse(BASE / "app" / "static" / "index.html")


@app.get("/api/civic/health")
def health() -> dict:
    return {"ok": True, "simulated": True, "tick": rt.env.tick, "clock": cfg.clock(rt.env.tick),
            "horizon": cfg.horizon_ticks, "episode_seed": rt.env.seed, "running": rt.running,
            "tick_interval_sec": rt.tick_interval, "tick_hours": cfg.tick_hours, "scenario": rt.scenario,
            "cause_types": [c.id for c in cfg.causes],
            "policy": effective_policy(), "policy_requested": rt.policy_name, "rl_loaded": rt.agent is not None,
            "rl_checkpoint": None if not rt.agent_meta else {k: rt.agent_meta[k] for k in ("episodes", "config_hash", "algorithm")},
            "llm_ok": rt.llm_ok, "portal_bridge": cfg.live.portal_bridge.enabled, "bridge_sent": rt.bridge_sent,
            "residents": len(rt.env.population), "last_error": rt.last_error}


@app.get("/api/civic/map")
def city_map() -> dict:
    city = rt.env.city
    depts = [{**d.model_dump(), "hq": {"block": city.block_name(city.node(*d.hq_block)),
                                       "lat": float(city.lat[city.node(*d.hq_block)]),
                                       "lon": float(city.lon[city.node(*d.hq_block)])}} for d in cfg.departments]
    return {"simulated": True, "departments": depts, "spacing_m": cfg.grid.spacing_m,
            "center": [cfg.grid.center_lat, cfg.grid.center_lon], "residents_per_block": cfg.citizens.per_block,
            "categories": [c.model_dump() for c in cfg.categories], **geometry(rt.env.city)}


@app.get("/api/civic/state")
def state() -> dict:
    env = rt.env
    win = env.portal.window(env.tick, cfg.tracer.window_ticks)
    dept_of = np.array([c.department == "police" for c in cfg.categories])
    return {
        "simulated": True, "tick": env.tick, "clock": cfg.clock(env.tick), "done": env.done,
        "blocks": [{"block": env.city.block_name(b), "potholes": int(env.potholes[b]),
                    "recent_municipal": int(win[b, ~dept_of].sum()), "recent_police": int(win[b, dept_of].sum())}
                   for b in range(env.city.n)],
        "queues": {d: len(env.portal.queue(d)) for d in env.departments},
        "actions": list(rt.actions)[-40:],
        "metrics": env.episode_metrics() | {"causes": None, "identified": None, "fixed": None, "ticks_to_identify": None},
    }


@app.get("/api/civic/complaints")
def complaints(since_tick: int = 0, department: str | None = None, limit: int = 200) -> list[dict]:
    env = rt.env
    out = [c for c in env.portal.complaints if c.tick >= since_tick and (department is None or c.department == department)]
    return [complaint_json(c, env) for c in out[-limit:]]


@app.get("/api/civic/diagnosis")
def diagnosis() -> dict:
    env = rt.env
    return root_cause_reports(cfg, env.city, env.portal, env.tick)


@app.get("/api/civic/traces")
def traces() -> list[dict]:
    return list(rt.traces)


@app.get("/api/civic/last_episode")
def last_episode() -> dict:
    """Previous finished episode with its ground truth revealed (for the demo's 'was it right?' moment)."""
    if rt.last_episode is None:
        raise HTTPException(404, "no finished episode yet")
    return rt.last_episode


class ReasonRequest(BaseModel):
    asset_name: str                              # a confirmed root cause or a hypothesis in the current diagnosis


@app.post("/api/civic/root-cause")
async def reason_root_cause(req: ReasonRequest) -> dict:
    """LLM reasoning (Groq gpt-oss-120b, fallbacks) over the public evidence for one root cause or hypothesis."""
    env = rt.env
    report = root_cause_reports(cfg, env.city, env.portal, env.tick)
    subject = next((r for r in report["root_causes"] if r["where"]["asset"] == req.asset_name), None)
    tick_key = None
    if subject is None:
        subject = next((h for h in report["hypotheses"] if h["asset_name"] == req.asset_name), None)
        tick_key = env.tick                       # hypotheses change every tick; confirmed reports do not
    if subject is None:
        raise HTTPException(404, f"{req.asset_name!r} is neither a confirmed root cause nor a current hypothesis")
    key = (env.seed, req.asset_name, subject["status"], tick_key)
    if key in rt.reasoning_cache:
        return {**rt.reasoning_cache[key], "cached": True}
    layer = subject["where"]["layer"] if "where" in subject else subject["layer"]
    work = [{"clock": cfg.clock(w.tick), "department": w.department, "action": w.action,
             "asset": env.city.layers[w.layer].assets[w.asset].name, "found_fault": w.found_fault, "policy": w.policy}
            for w in env.portal.work if w.layer == layer]
    evidence = reasoning.build_evidence(cfg, report, subject, work, env.episode_metrics(), effective_policy())
    out = await reasoning.root_cause(rt.client, cfg.live.root_cause, LLM_URL, cfg.live.llm_model, evidence, subject)
    out.update({"subject": req.asset_name, "status": subject["status"], "clock": cfg.clock(env.tick), "simulated": True})
    rt.reasoning_cache[key] = out
    return out


class ExplainRequest(BaseModel):
    action_id: str


@app.post("/api/civic/explain")
async def explain(req: ExplainRequest) -> dict:
    """Local Gemma explains one crew decision from what the policy saw; numbers are checked against the record."""
    rec = rt.decisions.get(req.action_id)
    if rec is None:
        raise HTTPException(404, "decision not in the recent log")
    out = await reasoning.explain_action(rt.client, LLM_URL, cfg.live.llm_model, cfg.live.llm_timeout_sec, rec)
    return {**out, "record": rec}


class ControlRequest(BaseModel):
    running: bool | None = None
    policy: str | None = None
    step: int = 0
    tick_interval_sec: float | None = None


@app.post("/api/civic/control")
async def control(req: ControlRequest) -> dict:
    if req.policy is not None:
        if req.policy not in POLICIES:
            raise HTTPException(422, f"policy must be one of {POLICIES}")
        rt.policy_name = req.policy
        rt.policies = {d: build_policy(effective_policy(), cfg, rt.agent, rt.env.seed + i)
                       for i, d in enumerate(rt.env.departments)}
    if req.running is not None:
        rt.running = req.running
    if req.tick_interval_sec is not None:
        rt.tick_interval = min(max(req.tick_interval_sec, 0.5), 15.0)
    results = [await tick_once() for _ in range(max(0, min(req.step, cfg.horizon_ticks)))]
    return {"running": rt.running, "policy": effective_policy(), "stepped": len(results), "tick": rt.env.tick,
            "tick_interval_sec": rt.tick_interval}


class ResetRequest(BaseModel):
    seed: int | None = None
    scenario: list[str] | None = None            # cause ids to plant; [] = control; null = random


@app.post("/api/civic/reset")
async def reset_endpoint(req: ResetRequest) -> dict:
    known = {c.id for c in cfg.causes}
    if req.scenario and set(req.scenario) - known:
        raise HTTPException(422, f"unknown cause types {sorted(set(req.scenario) - known)}; known: {sorted(known)}")
    async with rt.lock:
        reset(req.seed, req.scenario)
    return {"tick": rt.env.tick, "seed": rt.env.seed}
