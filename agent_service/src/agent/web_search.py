"""Web search for local area agents (Tavily).

Results are untrusted third-party text: callers must present them to the LLM as data, never as
instructions, and cite their URLs. Without TAVILY_API_KEY (or on any failure) this returns [] and the
local agent answers from its area context alone, saying that live web results were unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from src.config import settings

logger = logging.getLogger("citysense.web_search")

TAVILY_URL = "https://api.tavily.com/search"
MAX_SNIPPET_CHARS = 700


@dataclass
class WebResult:
    title: str
    url: str
    content: str


async def search(query: str, max_results: int = 5) -> list[WebResult]:
    if not settings.tavily_api_key:
        return []
    payload = {
        "api_key": settings.tavily_api_key.get_secret_value(),
        "query": query[:400],
        "max_results": max(1, min(max_results, 8)),
        "search_depth": "basic",
        "include_answer": False,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0)) as client:
            response = await client.post(TAVILY_URL, json=payload)
            response.raise_for_status()
            rows = response.json().get("results") or []
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("web search failed: %s", exc.__class__.__name__)
        return []
    results = []
    for row in rows:
        url = str(row.get("url") or "")
        if not url.startswith(("http://", "https://")):
            continue
        results.append(
            WebResult(
                title=str(row.get("title") or url)[:200],
                url=url[:500],
                content=" ".join(str(row.get("content") or "").split())[:MAX_SNIPPET_CHARS],
            )
        )
    return results
