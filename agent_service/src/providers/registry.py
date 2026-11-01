import asyncio
import time
from collections import defaultdict, deque

import httpx

from src.config import settings
from src.providers.base import GeneratedText
from src.providers.hosted import configured_providers
from src.providers.local import _extractive_answer

_semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
_failures: dict[str, int] = defaultdict(int)
_cooldown: dict[str, float] = defaultdict(float)
_requests: dict[str, deque[float]] = defaultdict(deque)


async def generate_with_failover(
    *,
    system: str,
    user: str,
    context: list[str],
    language: str | None,
    tools: list[dict] | None = None,
    history: list[dict] | None = None,
) -> GeneratedText:
    providers = configured_providers()
    async with _semaphore:
        for name in settings.providers:
            provider = providers.get(name)
            now = time.monotonic()
            if not provider or _cooldown[name] > now:
                continue
            queue = _requests[name]
            while queue and queue[0] <= now - 60:
                queue.popleft()
            if len(queue) >= settings.provider_rpm:
                continue
            for attempt in range(2):
                if len(queue) >= settings.provider_rpm:
                    break
                queue.append(time.monotonic())
                try:
                    result = await provider.generate(
                        system=system,
                        user=user,
                        context=context,
                        language=language,
                        tools=tools,
                        history=history,
                    )
                    _failures[name] = 0
                    return result
                except (
                    httpx.HTTPError,
                    ValueError,
                    KeyError,
                    IndexError,
                    TypeError,
                    AttributeError,
                ) as exc:
                    _failures[name] += 1
                    if _failures[name] >= 3:
                        _cooldown[name] = time.monotonic() + settings.provider_cooldown_seconds
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                        break
                    if attempt == 0:
                        await asyncio.sleep(0.1)

    if settings.demo_mode:
        return GeneratedText(_extractive_answer(context, language), "offline-extractive", True)
    raise RuntimeError("No text provider is available")
