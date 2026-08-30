"""Clients API — CRUD, soft-delete archival, mapping list/reset (Product Spec §10.2).

Archival WRITE-path gap (read-only for this prompt beyond clients):
- trial_balances: DELETE /trial-balances/{id} is specified in §10.2 and §12.2
  requires an archived_records snapshot on TB delete, but no delete handler or
  archive write exists yet.
- financial_statements: listed as an entity_type in archived_records DDL, but
  there is no delete/archive write path (statements are replaced in place on
  regenerate; no soft-delete column or archival call).
Only clients soft-delete writes archived_records in this slice.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import AuthContext, get_auth_context, get_db_session
from app.models.account_mapping import AccountMapping
from app.models.client import Client
from app.models.organisation import Organisation
from app.schemas.client import (
    BulkDeleteMappingsResponse,
    ClientCreateRequest,
    ClientListResponse,
    ClientMappingsResponse,
    ClientResponse,
    ClientUpdateRequest,
    MappingListItem,
)
from app.services.archival import archive_client_user_deleted

router = APIRouter(prefix="/clients", tags=["clients"])

_DEFAULT_PAGE = 20
_MAX_PAGE = 100


async def _get_owned_client(
    session: AsyncSession,
    *,
    client_id: uuid.UUID,
    org_id: uuid.UUID,
    include_deleted: bool = False,
) -> Client:
    """App-layer org ownership check — 404 for missing or cross-org (no 403 leak)."""
    clauses = [Client.id == client_id, Client.org_id == org_id]
    if not include_deleted:
        clauses.append(Client.is_deleted.is_(False))
    result = await session.execute(select(Client).where(*clauses))
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ClientResponse)
async def create_client(
    body: ClientCreateRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Client:
    await aset_rls_org_id(session, auth.org_id)
    org = await session.get(Organisation, auth.org_id)
    if org is None:
        raise HTTPException(status_code=401, detail="Unknown organisation")

    currency = (body.functional_currency or org.functional_currency or "GBP").upper()
    client = Client(
        org_id=auth.org_id,
        name=body.name.strip(),
        company_number=body.company_number,
        industry=body.industry,
        functional_currency=currency,
        # materiality_threshold_pct/abs use DB server defaults (10.00 / 1000.00)
    )
    session.add(client)
    await session.flush()
    await session.refresh(client)
    return client


@router.get("", response_model=ClientListResponse)
async def list_clients(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE)] = _DEFAULT_PAGE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientListResponse:
    await aset_rls_org_id(session, auth.org_id)
    base = select(Client).where(
        Client.org_id == auth.org_id,
        Client.is_deleted.is_(False),
    )
    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    )
    result = await session.execute(
        base.order_by(Client.created_at.desc()).limit(limit).offset(offset)
    )
    items = list(result.scalars().all())
    return ClientListResponse(
        items=[ClientResponse.model_validate(item) for item in items],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Client:
    await aset_rls_org_id(session, auth.org_id)
    return await _get_owned_client(session, client_id=client_id, org_id=auth.org_id)


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: uuid.UUID,
    body: ClientUpdateRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Client:
    await aset_rls_org_id(session, auth.org_id)
    client = await _get_owned_client(session, client_id=client_id, org_id=auth.org_id)
    updates = body.model_dump(exclude_unset=True)
    if "functional_currency" in updates and updates["functional_currency"] is not None:
        updates["functional_currency"] = updates["functional_currency"].upper()
    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()
    for field, value in updates.items():
        setattr(client, field, value)
    await session.flush()
    await session.refresh(client)
    return client


@router.delete("/{client_id}", status_code=status.HTTP_200_OK, response_model=ClientResponse)
async def soft_delete_client(
    client_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Client:
    """Soft delete + archived_records snapshot in the same transaction (§12.2).

    Both writes use this request's AsyncSession. ``flush`` only pushes SQL to the
    open transaction — the single ``commit`` is in ``get_db_session`` after the
    handler returns successfully. If ``archive_client_user_deleted`` raises, the
    dependency rolls back and the soft-delete is undone with the archive insert.
    """
    await aset_rls_org_id(session, auth.org_id)
    client = await _get_owned_client(session, client_id=client_id, org_id=auth.org_id)
    now = datetime.now(timezone.utc)
    client.is_deleted = True
    client.deleted_at = now
    await session.flush()
    await session.refresh(client)
    await archive_client_user_deleted(
        session,
        client=client,
        archived_by_user_id=auth.user_id,
        archived_at=now,
    )
    return client


@router.get("/{client_id}/mappings", response_model=ClientMappingsResponse)
async def list_client_mappings(
    client_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ClientMappingsResponse:
    await aset_rls_org_id(session, auth.org_id)
    await _get_owned_client(session, client_id=client_id, org_id=auth.org_id)
    result = await session.execute(
        select(AccountMapping)
        .where(
            AccountMapping.client_id == client_id,
            AccountMapping.is_confirmed.is_(True),
        )
        .order_by(AccountMapping.source_code, AccountMapping.source_name)
    )
    mappings = list(result.scalars().all())
    return ClientMappingsResponse(
        client_id=client_id,
        mappings=[MappingListItem.model_validate(row) for row in mappings],
    )


@router.delete(
    "/{client_id}/mappings",
    response_model=BulkDeleteMappingsResponse,
)
async def bulk_delete_client_mappings(
    client_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BulkDeleteMappingsResponse:
    """Bulk delete all account_mappings for a client (mapping reset)."""
    await aset_rls_org_id(session, auth.org_id)
    await _get_owned_client(session, client_id=client_id, org_id=auth.org_id)
    result = await session.execute(
        delete(AccountMapping)
        .where(AccountMapping.client_id == client_id)
        .returning(AccountMapping.id)
    )
    deleted_ids = result.scalars().all()
    return BulkDeleteMappingsResponse(
        client_id=client_id,
        deleted_count=len(deleted_ids),
    )
