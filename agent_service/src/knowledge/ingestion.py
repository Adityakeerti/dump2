import asyncio
import hashlib
import sys
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import session_factory
from src.knowledge.chunking import chunk_text
from src.knowledge.embeddings import get_embedder
from src.knowledge.schemas import DocumentMetadata
from src.models import AnswerCache, KnowledgeChunk, KnowledgeDocument, utcnow

_ingestion_slots = asyncio.Semaphore(2)


def hash_file(path: Path) -> str:
    if path.stat().st_size > settings.max_upload_bytes:
        raise ValueError("Document exceeds configured upload limit")
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def read_source(path: Path) -> str:
    if path.stat().st_size > settings.max_upload_bytes:
        raise ValueError("Document exceeds configured upload limit")
    if path.suffix.lower() == ".pdf":
        import pymupdf

        with pymupdf.open(path) as document:
            if document.is_encrypted:
                raise ValueError("Encrypted PDFs are unsupported")
            if len(document) > 1000:
                raise ValueError("PDF exceeds 1000 pages")
            parts = []
            size = 0
            for page in document:
                value = page.get_text()
                size += len(value)
                if size > 2_000_000:
                    raise ValueError("Extracted text exceeds processing limit")
                parts.append(value)
            return "\n\n".join(parts)
    if path.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("Only PDF, Markdown, and UTF-8 text are supported")
    return path.read_text(encoding="utf-8-sig")


async def parse_source(path: Path) -> str:
    process = await asyncio.create_subprocess_exec(sys.executable, "-m", "src.knowledge.parse_worker", str(path.resolve()), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        async with asyncio.timeout(settings.ingestion_timeout_seconds):
            output, _ = await process.communicate()
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode != 0:
        raise ValueError("Document parsing failed")
    return output.decode("utf-8")


async def process_document(doc_id: UUID) -> None:
    async with _ingestion_slots, session_factory() as session:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": str(doc_id)}
        )
        document = await session.get(KnowledgeDocument, doc_id)
        if not document:
            return
        if document.ingestion_status != "processing":
            return
        try:
            if not document.file_path:
                raise ValueError("Document has no stored source file")
            async with asyncio.timeout(settings.ingestion_timeout_seconds):
                digest = await asyncio.to_thread(hash_file, Path(document.file_path))
                if digest != document.content_hash:
                    document.verification_status = "unverified"
                    document.content_hash = digest
                content = await parse_source(Path(document.file_path))
                if not content.strip():
                    raise ValueError("Document has no extractable text; scanned PDFs require OCR")
                embedder = await asyncio.to_thread(get_embedder)
                tokenizer = getattr(getattr(embedder, "model", None), "tokenizer", None)
                counter = (
                    (lambda value: len(tokenizer.encode(value, add_special_tokens=False)))
                    if tokenizer
                    else None
                )
                chunks = await asyncio.to_thread(chunk_text, content, token_count=counter)
                vectors = await asyncio.to_thread(
                    lambda: [embedder.embed(f"passage: {c.text}") for c in chunks]
                )
            await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id))
            for chunk, vector in zip(chunks, vectors, strict=True):
                session.add(
                    KnowledgeChunk(
                        doc_id=doc_id,
                        tenant_id=document.tenant_id,
                        chunk_index=chunk.index,
                        section=chunk.section,
                        lang=document.language,
                        text=chunk.text,
                        embedding=vector,
                        embed_model=embedder.name,
                    )
                )
            document.ingestion_status = "ready"
            document.ingestion_error = None
            await session.execute(delete(AnswerCache))
            await session.commit()
        except Exception as exc:
            await session.rollback()
            document = await session.get(KnowledgeDocument, doc_id)
            if document:
                document.ingestion_status = "failed"
                document.ingestion_error = (
                    f"{type(exc).__name__}: document could not be parsed or indexed"
                )
                await session.commit()


async def register_file(
    session: AsyncSession, path: Path, metadata: DocumentMetadata
) -> KnowledgeDocument:
    digest = await asyncio.to_thread(hash_file, path)
    document = KnowledgeDocument(
        doc_id=uuid4(),
        **metadata.model_dump(exclude={"source_url"}),
        source_url=str(metadata.source_url) if metadata.source_url else None,
        content_hash=digest,
        file_path=str(path.resolve()),
        fetched_at=utcnow(),
        ingestion_status="processing",
        verification_status="unverified",
    )
    session.add(document)
    await session.commit()
    return document


async def ingest_file(
    session: AsyncSession,
    path: Path,
    *,
    tenant_id: str,
    title: str | None = None,
    metadata: DocumentMetadata | None = None,
) -> KnowledgeDocument:
    metadata = metadata or DocumentMetadata(
        tenant_id=tenant_id,
        title=title or path.stem,
        publisher="Local corpus",
        jurisdiction="national",
        language="en",
    )
    digest = await asyncio.to_thread(hash_file, path)
    existing = await session.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == tenant_id,
            or_(
                KnowledgeDocument.content_hash == digest,
                KnowledgeDocument.file_path == str(path.resolve()),
            ),
        )
    )
    if existing and existing.ingestion_status == "ready" and existing.content_hash == digest:
        return existing
    document = existing or await register_file(session, path, metadata)
    if existing:
        document.ingestion_status = "processing"
        if document.content_hash != digest:
            document.verification_status = "unverified"
            document.content_hash = digest
        document.file_path = str(path.resolve())
        await session.commit()
    await process_document(document.doc_id)
    await session.refresh(document)
    return document
