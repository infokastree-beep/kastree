"""Archived records retrieval (§10.2 / §12.2) — list + hash-verified get."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import AuthContext, get_auth_context, get_db_session, require_roles
from app.models.archived_record import ArchivedRecord
from app.models.client import Client
from app.schemas.archived_record import (
    ArchivedRecordDetailResponse,
    ArchivedRecordListResponse,
    ArchivedRecordSummary,
)
from app.services.archival import verify_archive_hash

clients_router = APIRouter(prefix="/clients", tags=["archived-records"])
org_router = APIRouter(prefix="/organisations", tags=["archived-records"])
records_router = APIRouter(prefix="/archived-records", tags=["archived-records"])

_ORG_LEVEL_REASONS = frozenset({"org_deleted", "subscription_cancelled"})


@clients_router.get(
    "/{client_id}/archived-records",
    response_model=ArchivedRecordListResponse,
)
async def list_client_archived_records(
    client_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_roles("owner", "admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    entity_type: Annotated[str | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
    period_end_from: Annotated[date | None, Query()] = None,
    period_end_to: Annotated[date | None, Query()] = None,
) -> ArchivedRecordListResponse:
    """Client-scoped archives (archive_reason = user_deleted). Admin+ only."""
    await aset_rls_org_id(session, auth.org_id)
    client = await session.scalar(
        select(Client).where(
            Client.id == client_id,
            Client.org_id == auth.org_id,
        )
    )
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")

    query = select(ArchivedRecord).where(
        ArchivedRecord.org_id == auth.org_id,
        ArchivedRecord.client_id == client_id,
        ArchivedRecord.archive_reason == "user_deleted",
    )
    if entity_type:
        query = query.where(ArchivedRecord.entity_type == entity_type)
    # period_end filters apply when archived_data carries period_end (TB snapshots).
    if period_end is not None:
        query = query.where(
            ArchivedRecord.archived_data["period_end"].as_string()
            == period_end.isoformat()
        )
    if period_end_from is not None:
        query = query.where(
            ArchivedRecord.archived_data["period_end"].as_string()
            >= period_end_from.isoformat()
        )
    if period_end_to is not None:
        query = query.where(
            ArchivedRecord.archived_data["period_end"].as_string()
            <= period_end_to.isoformat()
        )

    result = await session.execute(query.order_by(ArchivedRecord.created_at.desc()))
    items = list(result.scalars().all())
    return ArchivedRecordListResponse(
        items=[ArchivedRecordSummary.model_validate(item) for item in items]
    )


@org_router.get(
    "/me/archived-records",
    response_model=ArchivedRecordListResponse,
)
async def list_org_archived_records(
    auth: Annotated[AuthContext, Depends(require_roles("owner"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    entity_type: Annotated[str | None, Query()] = None,
    archive_reason: Annotated[str | None, Query()] = None,
) -> ArchivedRecordListResponse:
    """Org-level archives (client_id IS NULL). Owner only."""
    await aset_rls_org_id(session, auth.org_id)
    query = select(ArchivedRecord).where(
        ArchivedRecord.org_id == auth.org_id,
        ArchivedRecord.client_id.is_(None),
        ArchivedRecord.archive_reason.in_(_ORG_LEVEL_REASONS),
    )
    if entity_type:
        query = query.where(ArchivedRecord.entity_type == entity_type)
    if archive_reason:
        if archive_reason not in _ORG_LEVEL_REASONS:
            raise HTTPException(
                status_code=400,
                detail="archive_reason must be org_deleted or subscription_cancelled",
            )
        query = query.where(ArchivedRecord.archive_reason == archive_reason)

    result = await session.execute(query.order_by(ArchivedRecord.created_at.desc()))
    items = list(result.scalars().all())
    return ArchivedRecordListResponse(
        items=[ArchivedRecordSummary.model_validate(item) for item in items]
    )


@records_router.get(
    "/{record_id}",
    response_model=ArchivedRecordDetailResponse,
)
async def get_archived_record(
    record_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_roles("owner", "admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ArchivedRecordDetailResponse:
    """Full snapshot + server-side SHA-256 recompute → hash_verified (§10.2)."""
    await aset_rls_org_id(session, auth.org_id)
    result = await session.execute(
        select(ArchivedRecord).where(
            ArchivedRecord.id == record_id,
            ArchivedRecord.org_id == auth.org_id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Archived record not found")

    verified = verify_archive_hash(record.archived_data, record.archive_hash)
    return ArchivedRecordDetailResponse(
        id=record.id,
        org_id=record.org_id,
        client_id=record.client_id,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        archive_reason=record.archive_reason,
        archived_by_user_id=record.archived_by_user_id,
        archived_data=record.archived_data,
        archive_hash=record.archive_hash,
        retention_until=record.retention_until,
        created_at=record.created_at,
        hash_verified=verified,
    )
