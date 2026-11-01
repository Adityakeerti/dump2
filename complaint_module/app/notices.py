"""Government notices: published from the state govt portal, read by the citizen mobile app.

There is no database: notices live in ``STATE_DIR/notices.json`` next to ``complaints.json`` and are
written with the same atomic-replace pattern. Field names are camelCase because the portal's
existing notice schema (and the mobile app) already use them.
"""
import datetime
import hmac
import json
import os
import random
import re
import tempfile
import threading
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from . import pg_store
from .storage import STATE_DIR

NOTICES_FILE = os.path.join(STATE_DIR, "notices.json")
_LOCK = threading.RLock()

router = APIRouter(prefix="/api/notices", tags=["notices"])


def require_operator(x_operator_key: Optional[str] = Header(None)) -> None:
    """Publishing and revoking are operator actions: they need X-Operator-Key == $OPERATOR_KEY.
    Reading stays public (the citizen app's feed). Without a configured key, writes are disabled."""
    expected = os.getenv("OPERATOR_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Notice publishing is disabled: OPERATOR_KEY is not configured")
    if not x_operator_key or not hmac.compare_digest(x_operator_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing operator key")


class NoticeCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    hindiTitle: str = Field("", max_length=300)
    referenceNumber: str = Field("", max_length=120)
    department: str = Field(min_length=2, max_length=200)
    category: str = Field("Gazette Notification", max_length=80)
    priority: str = Field("Standard", max_length=40)
    signatory: str = Field("Competent Authority, Govt. of Uttarakhand", max_length=200)
    summary: str = Field("", max_length=1000)
    body: str = Field("", max_length=20000)
    expiryDate: Optional[str] = None
    isPinned: bool = False
    tags: List[str] = Field(default_factory=list, max_length=20)

    @field_validator("title", "department", "hindiTitle", "referenceNumber", "signatory", "summary", "body")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, v: List[str]) -> List[str]:
        return [t.strip()[:40] for t in v if t and t.strip()]

    @field_validator("expiryDate")
    @classmethod
    def _iso_date(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        _parse(v)  # raises ValueError -> 422
        return v


class Notice(NoticeCreate):
    id: str
    publishDate: str


def _parse(ts: str) -> datetime.datetime:
    dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def _load() -> List[Notice]:
    if pg_store.enabled():
        return [Notice(**n) for n in pg_store.list_notices()]
    if not os.path.exists(NOTICES_FILE):
        return []
    try:
        with open(NOTICES_FILE, "r", encoding="utf-8") as f:
            return [Notice(**n) for n in json.load(f)]
    except Exception as e:  # a corrupt file must not take the feed down
        print(f"[Notices] could not read {NOTICES_FILE}: {e}")
        return []


def _save(notices: List[Notice]) -> None:
    if pg_store.enabled():
        pg_store.replace_notices([n.model_dump() for n in notices])
        return
    with _LOCK:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(NOTICES_FILE), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump([n.model_dump() for n in notices], f, indent=2, ensure_ascii=False)
        os.replace(tmp, NOTICES_FILE)


def _is_active(n: Notice, now: datetime.datetime) -> bool:
    return not n.expiryDate or _parse(n.expiryDate) > now


@router.get("", response_model=List[Notice])
def list_notices(
    limit: int = Query(100, ge=1, le=500),
    include_expired: bool = Query(False, description="Also return notices past their expiryDate"),
):
    """Latest notices first. The mobile feed and the portal both read this."""
    now = datetime.datetime.now(datetime.timezone.utc)
    notices = [n for n in _load() if include_expired or _is_active(n, now)]
    notices.sort(key=lambda n: _parse(n.publishDate), reverse=True)
    return notices[:limit]


@router.post("", response_model=Notice, status_code=201, dependencies=[Depends(require_operator)])
def publish_notice(req: NoticeCreate):
    """Publish a notice from the govt portal (operator key required)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    dept_code = (re.sub(r"[^A-Za-z]", "", req.department)[:4] or "GOV").upper()
    notice = Notice(
        **req.model_dump(exclude={"referenceNumber", "expiryDate", "tags"}),
        id=f"NOT-{uuid.uuid4().hex[:10].upper()}",
        referenceNumber=req.referenceNumber or f"UK-GOV/{dept_code}/{now.year}/GZ-{random.randint(100, 999)}",
        publishDate=now.isoformat(),
        expiryDate=req.expiryDate or (now + datetime.timedelta(days=90)).isoformat(),
        tags=req.tags or [dept_code],
    )
    with _LOCK:
        notices = _load()
        notices.append(notice)
        _save(notices)
    return notice


@router.delete("/{notice_id}", status_code=204, dependencies=[Depends(require_operator)])
def revoke_notice(notice_id: str):
    with _LOCK:
        notices = _load()
        kept = [n for n in notices if n.id != notice_id]
        if len(kept) == len(notices):
            raise HTTPException(status_code=404, detail="Notice not found")
        _save(kept)
    return Response(status_code=204)
