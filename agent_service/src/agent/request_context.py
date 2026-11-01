"""Per-request context shared with tool handlers.

``user_bearer`` carries the citizen's own ``Authorization`` header so tools that read the citizen's
data from core (incidents, avatar directory) act with exactly the citizen's permissions — never with
a service credential. It is set by the agent endpoints and is empty for internal/offline calls.
"""

from contextvars import ContextVar

user_bearer: ContextVar[str | None] = ContextVar("user_bearer", default=None)
