"""LangGraph citizen agent (live mode only): observe -> write (local Gemma) -> validate -> [fallback] -> END.

The simulator has already decided WHAT happened, WHERE and WHEN (category, block, tick). The LLM only writes
the complaint in the resident's own words, the way the population agents in city_sim only pick categories.
Validation rejects text with digits (a resident must not invent counts, dates or house numbers the sim did
not produce) or text that is too short or too long. On any failure the persona template is kept, and the
trace says so. Training never calls the LLM.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Awaitable, Callable, TypedDict

import httpx
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import CivicConfig


class ComplaintText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=4, max_length=80)
    description: str = Field(min_length=15, max_length=320)


TEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"title": {"type": "string", "maxLength": 80}, "description": {"type": "string", "maxLength": 300}},
    "required": ["title", "description"],
}
DIGITS = re.compile(r"\d")


class CitizenState(TypedDict, total=False):
    citizen: dict[str, Any]
    incident: dict[str, Any]
    prompt: list[dict[str, str]]
    raw: str | None
    text: dict[str, str] | None
    written_by: str
    error: str | None
    steps: list[dict[str, Any]]


LlmCall = Callable[[list[dict[str, str]]], Awaitable[str]]


def make_llm(cfg: CivicConfig, client: httpx.AsyncClient) -> LlmCall:
    live = cfg.live

    async def call(messages: list[dict[str, str]]) -> str:
        res = await client.post(
            f"{live.llm_base_url}/chat/completions",
            json={"model": live.llm_model, "messages": messages, "temperature": 0.7, "max_tokens": 200,
                  "response_format": {"type": "json_schema", "json_schema": {"name": "complaint", "schema": TEXT_SCHEMA}}},
            timeout=live.llm_timeout_sec,
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]

    return call


def build_citizen_graph(llm: LlmCall):
    def step(state: CitizenState, node: str, t0: float, **info: Any) -> list[dict[str, Any]]:
        return state.get("steps", []) + [{"node": node, "ms": round((time.perf_counter() - t0) * 1000, 1), **info}]

    async def observe(state: CitizenState) -> CitizenState:
        t0 = time.perf_counter()
        c, inc = state["citizen"], state["incident"]
        system = ("You are a resident of Dehradun writing a short complaint to the city's grievance portal. "
                  "Write in plain everyday English, first person, one or two sentences. Do not use any digits, "
                  "dates, counts or house numbers. Reply with JSON only: {\"title\": ..., \"description\": ...}.")
        user = (f"You are a {c['persona']}. Problem you noticed near your home: {inc['label']}. "
                f"What you would typically say: \"{inc['template']}\"")
        return {"prompt": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "steps": step(state, "observe", t0)}

    async def write(state: CitizenState) -> CitizenState:
        t0 = time.perf_counter()
        try:
            raw = await llm(state["prompt"])
            return {"raw": raw, "error": None, "steps": step(state, "write", t0)}
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"[:200]
            return {"raw": None, "error": err, "steps": step(state, "write", t0, error=err)}

    async def validate(state: CitizenState) -> CitizenState:
        t0 = time.perf_counter()
        if state.get("raw") is None:
            return {"text": None, "steps": step(state, "validate", t0, ok=False)}
        try:
            t = ComplaintText.model_validate(json.loads(state["raw"]))
            if DIGITS.search(t.title + t.description):
                raise ValueError("text contains digits the simulator did not produce")
            return {"text": t.model_dump(), "written_by": "llm", "steps": step(state, "validate", t0, ok=True)}
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            err = str(exc)[:200]
            return {"text": None, "error": err, "steps": step(state, "validate", t0, ok=False, error=err)}

    async def fallback(state: CitizenState) -> CitizenState:
        t0 = time.perf_counter()
        inc = state["incident"]
        return {"text": {"title": inc["label"], "description": inc["template"]}, "written_by": "template",
                "steps": step(state, "fallback", t0)}

    g = StateGraph(CitizenState)
    for name, fn in (("observe", observe), ("write", write), ("validate", validate), ("fallback", fallback)):
        g.add_node(name, fn)
    g.set_entry_point("observe")
    g.add_edge("observe", "write")
    g.add_edge("write", "validate")
    g.add_conditional_edges("validate", lambda s: END if s.get("text") else "fallback", {END: END, "fallback": "fallback"})
    g.add_edge("fallback", END)
    return g.compile()
