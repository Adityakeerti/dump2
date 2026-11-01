from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from src.database import check_database

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    database_ready = await check_database()
    embedder_ready = getattr(request.app.state, "embedder_ready", False)
    if not database_ready or not embedder_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "database": database_ready, "embedder": embedder_ready},
        )
    return JSONResponse(content={"status": "ready", "database": True, "embedder": True})
