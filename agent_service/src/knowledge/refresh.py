import asyncio
import hashlib
import ipaddress
import logging
import socket
import time
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlalchemy import delete, select, update

from src.config import settings
from src.database import session_factory
from src.knowledge.ingestion import process_document
from src.models import AnswerCache, KnowledgeDocument, PendingAction, utcnow

logger = logging.getLogger("citysense")


async def validate_refresh_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed = {d.lower() for d in settings.refresh_allowed_domains}
    if (
        parsed.scheme != "https"
        or host not in allowed
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
    ):
        raise ValueError("Refresh URL must use HTTPS on an explicitly allowed host")
    addresses = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Refresh URL must resolve to public addresses")


async def refresh_document(doc_id) -> None:
    async with session_factory() as session:
        doc = await session.get(KnowledgeDocument, doc_id)
        if not doc or not doc.source_url or not doc.file_path:
            return
        await validate_refresh_url(doc.source_url)
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            async with client.stream("GET", doc.source_url) as response:
                response.raise_for_status()
                body = bytearray()
                async for part in response.aiter_bytes():
                    body.extend(part)
                    if len(body) > settings.max_upload_bytes:
                        raise ValueError("Source exceeds upload limit")
        digest = hashlib.sha256(body).hexdigest()
        if digest != doc.content_hash:
            from pathlib import Path

            suffix = Path(doc.file_path).suffix
            if suffix == ".pdf" and not body.startswith(b"%PDF-"):
                raise ValueError("Refresh response is not a PDF")
            path = settings.upload_dir / f"{uuid4()}{suffix}"
            await asyncio.to_thread(path.write_bytes, bytes(body))
            doc.file_path = str(path.resolve())
            doc.content_hash = digest
            doc.verification_status = "unverified"
            doc.ingestion_status = "processing"
            await session.execute(delete(AnswerCache))
        doc.fetched_at = utcnow()
        await session.commit()
        if doc.ingestion_status == "processing":
            await process_document(doc.doc_id)


async def maintenance_loop() -> None:
    last_refresh = 0.0
    while True:
        try:
            async with session_factory() as session:
                pending_docs = (
                    await session.scalars(
                        select(KnowledgeDocument.doc_id).where(
                            KnowledgeDocument.ingestion_status == "processing"
                        )
                    )
                ).all()
                await session.execute(
                    update(PendingAction)
                    .where(PendingAction.status == "pending", PendingAction.expires_at <= utcnow())
                    .values(status="expired")
                )
                await session.execute(
                    update(PendingAction)
                    .where(
                        PendingAction.status == "executing", PendingAction.expires_at <= utcnow()
                    )
                    .values(status="failed")
                )
                await session.commit()
                refresh_ids = (
                    (
                        await session.scalars(
                            select(KnowledgeDocument.doc_id).where(
                                KnowledgeDocument.source_url.is_not(None)
                            )
                        )
                    ).all()
                    if settings.refresh_allowed_domains and not settings.demo_mode and time.monotonic()-last_refresh >= settings.refresh_interval_seconds
                    else []
                )
            for doc_id in pending_docs:
                await process_document(doc_id)
            for doc_id in refresh_ids:
                try:
                    await refresh_document(doc_id)
                except Exception:
                    logger.warning("Source refresh failed", extra={"doc_id": str(doc_id)})
            if refresh_ids:
                last_refresh = time.monotonic()
        except Exception:
            logger.warning("Maintenance database unavailable")
        await asyncio.sleep(30)
