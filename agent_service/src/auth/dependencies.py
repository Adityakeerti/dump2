from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.schemas import Principal
from src.config import settings

bearer = HTTPBearer(auto_error=False)


def _decode(token: str) -> Principal:
    try:
        options = {
            "require": ["sub", "exp", "iat"],
            "verify_aud": bool(settings.jwt_audience),
            "verify_iss": bool(settings.jwt_issuer),
        }
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=settings.jwt_accepted_algorithms,
            audience=settings.jwt_audience or None,
            issuer=settings.jwt_issuer or None,
            options=options,
        )
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject.strip() or len(subject) > 200:
            raise ValueError("missing subject")
        # Core issues upper-case roles (CITIZEN / ADMIN); agent checks are lower-case.
        return Principal(user_id=str(subject), role=str(payload.get("role", "citizen")).lower())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token"
        ) from exc


async def current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required"
        )
    return _decode(credentials.credentials)


async def admin_principal(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
    if principal.role not in {"admin", "service"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required"
        )
    return principal
