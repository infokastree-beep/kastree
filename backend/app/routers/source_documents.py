"""Source-document upload. Stores bytes; does not parse workbooks."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import (
    AuthContext,
    enforce_product2_production_access,
    get_db_session,
    require_member_work,
    require_reader,
)
from app.models.source_document import SourceDocument
from app.schemas.source_document import SourceDocumentResponse
from app.services.ownership import get_owned_company
from app.services.source_storage import (
    SourceObjectStorage,
    get_source_storage,
    practice_storage_key,
)
from app.services.upload_security import UploadRejected, inspect_upload

router = APIRouter(
    prefix="/source-documents",
    tags=["source-documents"],
    dependencies=[Depends(enforce_product2_production_access)],
)

_IDEMPOTENCY_MAX = 200


def _require_idempotency_key(value: str | None) -> str:
    if value is None or not value.strip():
        raise HTTPException(status_code=400, detail="Idempotency-Key is required")
    key = value.strip()
    if len(key) > _IDEMPOTENCY_MAX or "\n" in key or "\r" in key:
        raise HTTPException(status_code=400, detail="Idempotency-Key is invalid")
    return key


def _as_detected_type(value: str) -> Literal["pdf", "xlsx", "csv"]:
    if value == "pdf" or value == "xlsx" or value == "csv":
        return cast(Literal["pdf", "xlsx", "csv"], value)
    raise HTTPException(status_code=500, detail="Stored document type is invalid")


def _to_response(document: SourceDocument) -> SourceDocumentResponse:
    return SourceDocumentResponse(
        id=document.id,
        company_id=document.company_id,
        detected_type=_as_detected_type(document.detected_type),
        byte_size=document.byte_size,
        sha256=document.sha256,
        original_filename=document.original_filename,
        created_at=document.created_at,
    )


async def _read_limited(file: UploadFile) -> bytes:
    from app.services.upload_security import MAX_UPLOAD_BYTES

    chunks: list[bytes] = []
    total = 0
    while True:
        block = await file.read(1024 * 1024)
        if not block:
            break
        total += len(block)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="File exceeds 50MB limit")
        chunks.append(block)
    return b"".join(chunks)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SourceDocumentResponse,
)
async def upload_source_document(
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[SourceObjectStorage, Depends(get_source_storage)],
    company_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
    idempotency_key: Annotated[str | None, Header()] = None,
) -> SourceDocumentResponse:
    key = _require_idempotency_key(idempotency_key)
    await aset_rls_org_id(session, auth.org_id)
    company = await get_owned_company(
        session, company_id=company_id, org_id=auth.org_id
    )
    if company.org_id != auth.org_id:
        raise HTTPException(status_code=404, detail="Company not found")

    existing = (
        await session.execute(
            select(SourceDocument).where(
                SourceDocument.org_id == auth.org_id,
                SourceDocument.idempotency_key == key,
            )
        )
    ).scalar_one_or_none()

    content = await _read_limited(file)
    try:
        inspected = inspect_upload(content, file.filename)
    except UploadRejected as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc

    digest = hashlib.sha256(content).hexdigest()
    if existing is not None:
        if existing.sha256 == digest and existing.company_id == company.id:
            return _to_response(existing)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used for a different file",
        )

    document_id = uuid.uuid4()
    storage_key = practice_storage_key(
        org_id=auth.org_id,
        company_id=company.id,
        document_id=document_id,
    )
    document = SourceDocument(
        id=document_id,
        org_id=auth.org_id,
        company_id=company.id,
        storage_key=storage_key,
        original_filename=inspected.filename,
        detected_type=inspected.detected_type,
        byte_size=len(content),
        sha256=digest,
        idempotency_key=key,
        created_by_user_id=auth.user_id,
    )
    session.add(document)
    try:
        await session.flush()
    except IntegrityError as exc:
        if "findraft_source_documents_idempotency_key" not in str(exc.orig):
            raise
        await session.rollback()
        await aset_rls_org_id(session, auth.org_id)
        raced = (
            await session.execute(
                select(SourceDocument).where(
                    SourceDocument.org_id == auth.org_id,
                    SourceDocument.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        if raced is not None and raced.sha256 == digest and raced.company_id == company.id:
            return _to_response(raced)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used for a different file",
        ) from exc

    await asyncio.to_thread(
        storage.put,
        key=storage_key,
        body=content,
        content_type=inspected.content_type,
    )
    return _to_response(document)


@router.get(
    "/{document_id}",
    response_model=SourceDocumentResponse,
)
async def get_source_document(
    document_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SourceDocumentResponse:
    await aset_rls_org_id(session, auth.org_id)
    document = (
        await session.execute(
            select(SourceDocument).where(
                SourceDocument.id == document_id,
                SourceDocument.org_id == auth.org_id,
            )
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    return _to_response(document)
