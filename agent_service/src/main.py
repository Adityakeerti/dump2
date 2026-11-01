import asyncio
import contextlib
import json
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from src.config import settings
from src.database import engine
from src.logging_config import configure_logging
from src.middleware import BodyLimitMiddleware

logger = logging.getLogger("citysense")
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(application: FastAPI):
    if len(settings.jwt_secret.get_secret_value()) < 32:
        raise RuntimeError(
            "JWT_SECRET must contain at least 32 characters; run python -m scripts.bootstrap"
        )
    application.state.embedder_ready = False
    from src.knowledge.embeddings import get_embedder

    try:
        vector = await asyncio.to_thread(lambda: get_embedder().embed("query: readiness probe"))
        application.state.embedder_ready = len(vector) == 384
    except Exception:
        logger.error("Embedder failed to warm; readiness will remain unavailable")
    from src.knowledge.refresh import maintenance_loop

    maintenance = asyncio.create_task(maintenance_loop())
    yield
    maintenance.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await maintenance
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_upload_bytes + 65536)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID", "X-CitySense-Source"],
)


@app.middleware("http")
async def request_id(request: Request, call_next):
    identifier = str(uuid4())
    request.state.request_id = identifier
    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = identifier
    logger.info(
        json.dumps(
            {
                "request_id": identifier,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            }
        )
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # FastAPI's default includes input values; do not echo tokens or uploaded bodies.
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "detail": [
                {"loc": list(e["loc"]), "type": e["type"], "msg": e["msg"]} for e in exc.errors()
            ],
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    return JSONResponse(
        status_code=503,
        content={
            "code": "DATABASE_UNAVAILABLE",
            "requestId": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "code": "INTERNAL_SERVER_ERROR"},
    )


from fastapi.responses import HTMLResponse  # noqa: E402

from src.admin import router as admin_router  # noqa: E402
from src.agent.offline import get_all_complaints, resolve_complaint_by_id  # noqa: E402
from src.agent.router import router as agent_router  # noqa: E402
from src.auth.router import router as auth_router  # noqa: E402
from src.health.router import router as health_router  # noqa: E402
from src.knowledge.router import router as knowledge_router  # noqa: E402

for router in (health_router, auth_router, agent_router, knowledge_router, admin_router):
    app.include_router(router)


@app.get("/api/complaints")
async def list_complaints():
    return get_all_complaints()


@app.post("/api/complaints/{tracking_id}/resolve")
async def resolve_complaint(tracking_id: str, request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    note = body.get("resolution_note", "Work order completed and inspected on site.")
    updated = resolve_complaint_by_id(tracking_id, note)
    if not updated:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Complaint not found")
    return updated


@app.get("/ui", include_in_schema=False)
@app.get("/", include_in_schema=False)
async def serve_ui():
    # The single-file UI.html dashboards were retired (kept in Project/residuals/); the operator
    # dashboard is the React app in Project/dashboard/.
    return HTMLResponse(
        "<h2>CitySense Agent Service</h2><p>Service is running. API docs: <a href='docs'>/docs</a> · "
        "health: <a href='health'>/health</a>. The operator dashboard is the React app in "
        "<code>dashboard/</code> (dev: <a href='http://localhost:5173'>http://localhost:5173</a>).</p>"
    )

