"""Citizen photos attached to a drafted action (e.g. complaint evidence), stored in Postgres.

The photo is linked to the pending action by its token rather than written into the action's args,
because args are integrity-hashed at proposal time. On confirm, the photo travels with the complaint
to the complaint module. Without a database (offline engine) photos are kept in memory.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Principal
from src.models import Media, PendingAction, utcnow

MAX_BYTES = 10 * 1024 * 1024
OFFLINE_MEDIA: dict[str, dict[str, Any]] = {}

# Magic bytes -> content type: never trust the client's declared type or filename.
_SIGNATURES = [
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
]


def sniff(data: bytes) -> tuple[str, str] | None:
    for sig, ctype, ext in _SIGNATURES:
        if data.startswith(sig):
            return ctype, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return "image/heic", "heic"
    return None


async def attach_photo(session: AsyncSession, principal: Principal, token: str, data: bytes) -> dict[str, Any]:
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413, "Photo must be non-empty and at most 10 MB")
    kind = sniff(data)
    if not kind:
        raise HTTPException(415, "Only JPEG, PNG, WebP or HEIC photos are accepted")
    ctype, ext = kind
    filename = f"evidence.{ext}"
    try:
        action = await session.scalar(
            select(PendingAction).where(PendingAction.token == token, PendingAction.user_id == principal.user_id)
        )
    except Exception:
        action = None
        await session.rollback()
    if action is not None:
        if action.status != "pending" or action.expires_at <= utcnow():
            raise HTTPException(409, "This draft is no longer open for changes")
        await session.execute(delete(Media).where(Media.action_token == token))
        media = Media(user_id=principal.user_id, action_token=token, content_type=ctype, filename=filename,
                      size_bytes=len(data), data=data)
        session.add(media)
        await session.commit()
        return {"mediaId": str(media.media_id), "contentType": ctype, "sizeBytes": len(data)}

    from src.agent.offline import PENDING_ACTIONS

    offline = PENDING_ACTIONS.get(token)
    if not offline or offline.get("user_id") not in (None, principal.user_id):
        raise HTTPException(404, "Draft not found")
    if offline["status"] != "pending":
        raise HTTPException(409, "This draft is no longer open for changes")
    media_id = str(uuid4())
    OFFLINE_MEDIA[token] = {"mediaId": media_id, "user_id": principal.user_id, "data": data,
                            "content_type": ctype, "filename": filename}
    return {"mediaId": media_id, "contentType": ctype, "sizeBytes": len(data)}


async def photo_for(session: AsyncSession | None, token: str) -> tuple[bytes, str, str] | None:
    """(data, content_type, filename) of the photo attached to a draft, if any."""
    if session is not None:
        try:
            media = await session.scalar(
                select(Media).where(Media.action_token == token).order_by(Media.created_at.desc()).limit(1)
            )
            if media:
                return media.data, media.content_type, media.filename
        except Exception:
            pass
    item = OFFLINE_MEDIA.get(token)
    return (item["data"], item["content_type"], item["filename"]) if item else None


async def get_owned(session: AsyncSession, principal: Principal, media_id: UUID) -> Media:
    media = await session.get(Media, media_id)
    if not media or media.user_id != principal.user_id:
        raise HTTPException(404, "Photo not found")
    return media
