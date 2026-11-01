import time
from collections import OrderedDict, deque

from fastapi import HTTPException

from src.config import settings

_turns: OrderedDict[str, deque[float]] = OrderedDict()


def check_rate_limit(user_id: str) -> None:
    now = time.monotonic()
    while _turns and next(iter(_turns.values()))[-1] <= now - 60:
        _turns.popitem(last=False)
    queue = _turns.setdefault(user_id, deque())
    while queue and queue[0] <= now - 60:
        queue.popleft()
    if len(queue) >= settings.rate_limit_per_minute:
        raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": "60"})
    queue.append(now)
    _turns.move_to_end(user_id)
    if len(_turns) > 10000:
        _turns.popitem(last=False)
