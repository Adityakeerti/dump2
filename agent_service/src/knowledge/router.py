import asyncio
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import admin_principal
from src.auth.schemas import Principal
from src.config import settings
from src.database import get_session
from src.knowledge.ingestion import process_document, register_file
from src.knowledge.schemas import DocumentMetadata, DocumentView, VerificationRequest
from src.models import AnswerCache, AuditLog, KnowledgeDocument

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
Session = Annotated[AsyncSession, Depends(get_session)]
Admin = Annotated[Principal, Depends(admin_principal)]


@router.post("/docs", response_model=DocumentView, status_code=202)
async def upload(
    session: Session,
    principal: Admin,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    metadata: Annotated[str, Form()],
):
    try:
        parsed = DocumentMetadata.model_validate_json(metadata)
    except ValidationError as exc:
        raise HTTPException(422, "metadata must be valid DocumentMetadata JSON") from exc
    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".pdf", ".md", ".txt"}:
        raise HTTPException(415, "Only PDF, MD, and TXT documents are accepted")
    data = await file.read(settings.max_upload_bytes + 1)
    if not data or len(data) > settings.max_upload_bytes:
        raise HTTPException(
            413, "Document must be nonempty and at most the configured upload limit"
        )
    if extension == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(415, "Invalid PDF signature")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    path = settings.upload_dir / f"{uuid4()}{extension}"
    await asyncio.to_thread(path.write_bytes, data)
    try:
        doc = await register_file(session, path, parsed)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    session.add(
        AuditLog(
            actor=principal.user_id, event="document_uploaded", detail={"doc_id": str(doc.doc_id)}
        )
    )
    await session.commit()
    background.add_task(process_document, doc.doc_id)
    return doc


@router.get("/docs", response_model=list[DocumentView])
async def list_documents(
    session: Session,
    principal: Admin,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return (
        await session.scalars(
            select(KnowledgeDocument)
            .order_by(KnowledgeDocument.fetched_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()


@router.get("/docs/{doc_id}", response_model=DocumentView)
async def get_document(doc_id: UUID, session: Session, principal: Admin):
    doc = await session.get(KnowledgeDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.post("/docs/{doc_id}/verify", response_model=DocumentView)
async def verify(doc_id: UUID, payload: VerificationRequest, session: Session, principal: Admin):
    doc = await session.get(KnowledgeDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if payload.status == "verified" and doc.ingestion_status != "ready":
        raise HTTPException(409, "Only successfully indexed documents can be verified")
    doc.verification_status = payload.status
    session.add(
        AuditLog(
            actor=principal.user_id,
            event="document_verification",
            detail={"doc_id": str(doc_id), "status": payload.status},
        )
    )
    await session.execute(delete(AnswerCache))
    await session.commit()
    return doc


@router.post("/docs/{doc_id}/reindex", response_model=DocumentView, status_code=202)
async def reindex(doc_id: UUID, session: Session, principal: Admin, background: BackgroundTasks):
    doc = await session.get(KnowledgeDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if not doc.file_path:
        raise HTTPException(409, "Document has no stored file")
    if doc.ingestion_status == "processing":
        raise HTTPException(409, "Document is already processing")
    doc.ingestion_status = "processing"
    await session.commit()
    background.add_task(process_document, doc_id)
    return doc
