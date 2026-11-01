"""Population simulator service: runs LangGraph people-cluster agents against the live twin.

Run: uvicorn app.server:app --port 8004   (from city_sim/, SmartCity venv)
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import math
import os
import random
import re
import time
from collections import deque
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agents import build_graph, clock, make_llm, route_conditions
from app import root_cause
from app.config import ClusterConfig, load_config
from app.population import generate_clusters

BASE = Path(__file__).resolve().parent.parent
cfg = load_config(os.environ.get("CITY_SIM_CONFIG", BASE / "config.yaml"))
TWIN = os.environ.get("TWIN_URL", cfg.twin_url)
LLM = os.environ.get("LLM_BASE_URL", cfg.llm_base_url)
cfg = cfg.model_copy(update={"twin_url": TWIN, "llm_base_url": LLM})

METERS_PER_DEG_LAT = 111_320.0


class Runtime:
    def __init__(self) -> None:
        self.walk_paths: dict[str, list[list[float]]] = {}
        self.enabled = True
        self.client: httpx.AsyncClient | None = None
        self.graph = None
        self.topology: dict[str, Any] | None = None
        self.episode: int | None = None
        self.next_plan_at = 0.0
        self.round_running = False
        self.rounds = 0
        self.ids = itertools.count(1)
        self.traces: deque[dict[str, Any]] = deque(maxlen=cfg.trace_log_size)
        self.clusters: list[ClusterConfig] = []
        self.memory: dict[str, deque[dict[str, Any]]] = {}
        self.last_plan: dict[str, dict[str, Any]] = {}
        self.stats: dict[str, dict[str, Any]] = {}
        self.twin_ok = False
        self.llm_ok: bool | None = None
        self.last_error: str | None = None


rt = Runtime()


async def post_trips(trips: list[dict[str, Any]]) -> dict[str, Any]:
    res = await rt.client.post(f"{TWIN}/api/twin/trips", json={"trips": trips}, timeout=10)
    res.raise_for_status()
    return res.json()


def cluster_location(c: ClusterConfig) -> list[float] | None:
    if not rt.topology:
        return None
    src = next((s for s in rt.topology["geometry"]["sources"] if s["id"] == c.source_id), None)
    if src is None:
        return None
    dx, dy = c.offset_m
    lat = src["lat"] + dy / METERS_PER_DEG_LAT
    lon = src["lon"] + dx / (METERS_PER_DEG_LAT * math.cos(math.radians(src["lat"])))
    return [lat, lon]


WALK_CACHE = BASE / cfg.walk_cache_path


def set_clusters() -> None:
    """Explicit clusters from config, or a seeded random population over the twin's real geometry."""
    if cfg.population and cfg.population.generate:
        rt.clusters = generate_clusters(cfg.population, rt.topology)
    else:
        rt.clusters = list(cfg.clusters)
    for c in rt.clusters:
        rt.memory.setdefault(c.id, deque(maxlen=cfg.memory_size))
        rt.stats.setdefault(c.id, {"plans": 0, "llm": 0, "fallback": 0, "trips": 0, "vehicles": 0.0})


def _walk_key(c: ClusterConfig, start: list[float], end: list[float]) -> str:
    return f"{c.id}:{start[0]:.5f},{start[1]:.5f}->{end[0]:.5f},{end[1]:.5f}"


async def ensure_walk_paths() -> None:
    """Real footpaths from each neighbourhood to its corridor entry (cached; straight line if unavailable)."""
    cache: dict[str, list[list[float]]] = {}
    if WALK_CACHE.is_file():
        with contextlib.suppress(Exception):
            cache = json.loads(WALK_CACHE.read_text())
    changed = False
    for c in rt.clusters:
        start = cluster_location(c)
        src = next((s for s in rt.topology["geometry"]["sources"] if s["id"] == c.source_id), None)
        if start is None or src is None:
            continue
        end = [src["lat"], src["lon"]]
        key = _walk_key(c, start, end)
        if key not in cache and cfg.walk_router_url:
            try:
                res = await rt.client.get(
                    f"{cfg.walk_router_url}/{start[1]},{start[0]};{end[1]},{end[0]}",
                    params={"overview": "full", "geometries": "geojson"}, timeout=20,
                )
                coords = res.json()["routes"][0]["geometry"]["coordinates"]
                cache[key] = [start] + [[p[1], p[0]] for p in coords] + [end]
                changed = True
            except Exception as exc:
                rt.last_error = f"walk path {c.id}: {type(exc).__name__}"[:200]
        rt.walk_paths[c.id] = cache.get(key) or [start, end]
    if changed:
        WALK_CACHE.parent.mkdir(parents=True, exist_ok=True)
        WALK_CACHE.write_text(json.dumps(cache))


async def refresh_outcomes() -> None:
    """Attach realised delays of finished car clusters to each plan in cluster memory."""
    try:
        res = await rt.client.get(f"{TWIN}/api/twin/platoons", params={"limit": 300}, timeout=5)
        finished = res.json().get("finished", [])
    except Exception:
        return
    by_plan: dict[str, list[float]] = {}
    for p in finished:
        if p.get("delay_sec") is not None:
            by_plan.setdefault(p.get("plan_id") or "", []).append(p["delay_sec"])
    for mem in rt.memory.values():
        for m in mem:
            d = by_plan.get(m["plan_id"])
            if d:
                m["mean_delay_sec"] = sum(d) / len(d)
                m["car_clusters_finished"] = len(d)


async def run_round(state: dict[str, Any]) -> None:
    rt.round_running = True
    rt.rounds += 1
    sem = asyncio.Semaphore(cfg.max_concurrent_llm)
    await refresh_outcomes()

    async def one(c: ClusterConfig) -> None:
        async with sem:
            plan_id = f"P{next(rt.ids)}-{c.id}"
            obs = {
                "clock": clock(state["sim_time"], cfg.clock_start),
                "sim_time": state["sim_time"],
                "episode": state["episode"],
                "plan_id": plan_id,
                "route": route_conditions(c, state, rt.topology),
            }
            t0 = time.perf_counter()
            out = await rt.graph.ainvoke(
                {"cluster": c.model_dump(), "observation": obs, "memory": list(rt.memory[c.id]), "steps": []}
            )
            plan = out.get("plan") or {}
            trips = out.get("trips", [])
            veh = round(sum(t["vehicles"] for t in trips), 1)
            st = rt.stats[c.id]
            st["plans"] += 1
            st["llm" if out.get("decided_by") == "llm" else "fallback"] += 1
            st["trips"] += len(trips)
            st["vehicles"] = round(st["vehicles"] + veh, 1)
            rt.llm_ok = out.get("decided_by") == "llm"
            trace = {
                "id": plan_id,
                "ts": time.time(),
                "cluster_id": c.id,
                "cluster": c.name,
                "episode": state["episode"],
                "sim_time": state["sim_time"],
                "clock": obs["clock"],
                "decided_by": out.get("decided_by"),
                "plan": plan,
                "observation": obs["route"],
                "car_clusters": len(trips),
                "vehicles": veh,
                "steps": out.get("steps", []),
                "total_ms": round((time.perf_counter() - t0) * 1000, 1),
            }
            rt.traces.append(trace)
            rt.last_plan[c.id] = trace
            rt.memory[c.id].append({"plan_id": plan_id, "clock": obs["clock"], "episode": state["episode"], **{k: plan.get(k) for k in ("intent", "departure", "share")}})

    try:
        await asyncio.gather(*(one(c) for c in rt.clusters))
    finally:
        rt.round_running = False


async def loop() -> None:
    while True:
        try:
            if rt.topology is None:
                rt.topology = (await rt.client.get(f"{TWIN}/api/twin/topology", timeout=5)).json()
                set_clusters()
                await ensure_walk_paths()
            state = (await rt.client.get(f"{TWIN}/api/twin/state", timeout=5)).json()
            rt.twin_ok = True
            if state["episode"] != rt.episode:
                rt.episode = state["episode"]
                rt.next_plan_at = state["sim_time"]
            if rt.enabled and state["status"] == "running" and not rt.round_running and state["sim_time"] >= rt.next_plan_at:
                rt.next_plan_at = state["sim_time"] + cfg.planning_interval_sim_sec
                asyncio.create_task(run_round(state))
        except Exception as exc:
            rt.twin_ok = False
            rt.last_error = f"{type(exc).__name__}: {exc}"[:200]
        await asyncio.sleep(cfg.poll_interval_sec)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    rt.client = httpx.AsyncClient()
    rt.graph = build_graph(cfg, make_llm(cfg, rt.client), post_trips, random.Random(cfg.seed))
    task = asyncio.create_task(loop())
    yield
    task.cancel()
    await rt.client.aclose()


app = FastAPI(title="CitySense Population Simulator", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/city/health")
async def health() -> dict[str, Any]:
    llm = False
    with contextlib.suppress(Exception):
        llm = (await rt.client.get(LLM.removesuffix("/v1") + "/health", timeout=2)).status_code == 200
    return {
        "status": "ok",
        "twin": rt.twin_ok,
        "llm_server": llm,
        "llm_model": cfg.llm_model,
        "enabled": rt.enabled,
        "rounds": rt.rounds,
        "round_running": rt.round_running,
        "next_plan_at_sim_sec": rt.next_plan_at,
        "planning_interval_sim_sec": cfg.planning_interval_sim_sec,
        "last_error": rt.last_error,
    }


@app.get("/api/city/clusters")
async def clusters() -> dict[str, Any]:
    return {
        "clusters": [
            {
                **c.model_dump(),
                "location": cluster_location(c),
                "walk_path": rt.walk_paths.get(c.id),
                "last": rt.last_plan.get(c.id),
                "memory": list(rt.memory[c.id]),
                "stats": rt.stats[c.id],
            }
            for c in rt.clusters
        ],
        "generated": bool(cfg.population and cfg.population.generate),
        "total_population": sum(c.population for c in rt.clusters),
    }


@app.get("/api/city/traces")
async def traces(after_ts: float = 0.0, limit: int = 50) -> dict[str, Any]:
    items = [t for t in rt.traces if t["ts"] > after_ts][-max(1, min(limit, cfg.trace_log_size)):]
    return {"traces": items}


class ControlIn(BaseModel):
    enabled: bool | None = None
    plan_now: bool = False


@app.post("/api/city/control")
async def control(body: ControlIn) -> dict[str, Any]:
    if body.enabled is not None:
        rt.enabled = body.enabled
    if body.plan_now:
        rt.next_plan_at = 0.0
    return await health()


class ExplainIn(BaseModel):
    decision: dict[str, Any]


NUM = re.compile(r"-?\d+(?:\.\d+)?")


def grounded(text: str, source: str) -> bool:
    """Every number in the LLM text must appear in the decision record (tolerant to rounding)."""
    have = [float(x) for x in NUM.findall(source)]
    for tok in NUM.findall(text):
        v = float(tok)
        if not any(abs(v - h) <= max(0.051, abs(h) * 0.01) for h in have):
            return False
    return True


@app.post("/api/city/explain")
async def explain(body: ExplainIn) -> dict[str, Any]:
    d = body.decision
    keep = {k: d.get(k) for k in ("policy", "junction", "sim_time", "mode", "epsilon", "q", "shield", "switched",
                                   "prev_phase", "executed_phase", "art_queue", "cross_queue", "rule", "text")}
    keep["junction_label"] = f"J{int(d.get('junction', 0)) + 1}"
    keep["features"] = d.get("features")
    keep["attribution_top3"] = (d.get("attribution") or [])[:3]

    source = json.dumps(keep)
    messages = [
        {"role": "system", "content": (
            "You explain traffic-signal decisions made by a reinforcement-learning controller in a simulated "
            "corridor to a city operator. Phase 0 = arterial green, phase 1 = cross-street green. 'explore' means a "
            "random action taken for learning; 'exploit' means the action with the higher Q-value; a shield is a "
            "safety rule overriding the policy. Attribution contributions are positive when a feature pushed towards "
            "switching. Use at most 3 sentences, plain language, and do not state any number that is not in the record."
        )},
        {"role": "user", "content": f"Decision record: {source}"},
    ]
    try:
        res = await rt.client.post(
            f"{LLM}/chat/completions",
            json={"model": cfg.llm_model, "messages": messages, "temperature": 0.2, "max_tokens": 180},
            timeout=cfg.llm_timeout_sec,
        )
        res.raise_for_status()
        text = res.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {type(exc).__name__}") from exc
    ok = grounded(text, source)
    return {
        "explanation": text if ok else d.get("text"),
        "llm_text": text,
        "grounded": ok,
        "note": None if ok else "LLM mentioned numbers absent from the record; showing the deterministic explanation.",
        "model": cfg.llm_model,
    }


class RootCauseIn(BaseModel):
    cell: int
    diagnosis: dict[str, Any] | None = None  # pass the twin's /api/twin/diagnose result to avoid re-running it


@app.post("/api/city/root-cause")
async def trace_root_cause(body: RootCauseIn) -> dict[str, Any]:
    """Runs the twin's deterministic root-cause trace for a cell, then has the LLM reason over the evidence."""
    if cfg.root_cause is None:
        raise HTTPException(status_code=503, detail="root_cause is not configured in config.yaml")
    t0 = time.perf_counter()
    diagnosis = body.diagnosis
    if diagnosis is None:
        try:
            res = await rt.client.post(f"{TWIN}/api/twin/diagnose", json={"cell": body.cell}, timeout=120)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"twin unreachable: {type(exc).__name__}") from exc
        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail=res.json().get("detail", res.text))
        diagnosis = res.json()
    if not diagnosis.get("found"):
        return {"diagnosis": diagnosis, "llm": None, "total_ms": round((time.perf_counter() - t0) * 1000)}
    if rt.topology is None:
        with contextlib.suppress(Exception):
            rt.topology = (await rt.client.get(f"{TWIN}/api/twin/topology", timeout=5)).json()
    llm = await root_cause.reason(rt.client, diagnosis, rt.topology, cfg.root_cause.model_dump(), LLM, cfg.llm_model)
    return {"diagnosis": diagnosis, "llm": llm, "total_ms": round((time.perf_counter() - t0) * 1000)}
