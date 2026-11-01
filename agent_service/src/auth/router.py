from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException

from src.auth.dependencies import current_principal
from src.auth.schemas import DevTokenRequest, DevTokenResponse, Principal
from src.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/dev-token", response_model=DevTokenResponse)
async def dev_token(payload: DevTokenRequest) -> DevTokenResponse:
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Not found")
    claims = {
        "sub": payload.user_id,
        "role": payload.role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
    }
    if settings.jwt_issuer:
        claims["iss"] = settings.jwt_issuer
    if settings.jwt_audience:
        claims["aud"] = settings.jwt_audience
    return DevTokenResponse(
        token=jwt.encode(
            claims, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
        )
    )


@router.get("/me", response_model=Principal)
async def me(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
    return principal
