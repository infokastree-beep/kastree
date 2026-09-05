"""Clients API — CRUD for client groups; companies nested under /clients/{id}/companies."""

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
from app.models.company import Company
from app.models.organisation import Organisation
from app.schemas.client import (
    ClientCreateRequest,
    ClientListResponse,
    ClientResponse,
    ClientUpdateRequest,
)
from app.schemas.company import (
    ClientGroupBulkDeleteMappingsResponse,
    ClientGroupMappingsResponse,
    CompanyCreateRequest,
    CompanyListResponse,
    CompanyResponse,
    MappingListItem,
)
from app.services.archival import archive_client_user_deleted
from app.services.ownership import get_owned_client

router = APIRouter(prefix="/clients", tags=["clients"])

_DEFAULT_PAGE = 20
_MAX_PAGE = 100


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

    client = Client(
        org_id=auth.org_id,
        name=body.name.strip(),
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
    return await get_owned_client(session, client_id=client_id, org_id=auth.org_id)


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: uuid.UUID,
    body: ClientUpdateRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Client:
    await aset_rls_org_id(session, auth.org_id)
    client = await get_owned_client(session, client_id=client_id, org_id=auth.org_id)
    updates = body.model_dump(exclude_unset=True)
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
    """Soft delete + archived_records snapshot in the same transaction (§12.2)."""
    await aset_rls_org_id(session, auth.org_id)
    client = await get_owned_client(session, client_id=client_id, org_id=auth.org_id)
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


@router.post(
    "/{client_id}/companies",
    status_code=status.HTTP_201_CREATED,
    response_model=CompanyResponse,
)
async def create_company_for_client(
    client_id: uuid.UUID,
    body: CompanyCreateRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Company:
    await aset_rls_org_id(session, auth.org_id)
    client = await get_owned_client(session, client_id=client_id, org_id=auth.org_id)
    org = await session.get(Organisation, auth.org_id)
    if org is None:
        raise HTTPException(status_code=401, detail="Unknown organisation")

    currency = (body.functional_currency or org.functional_currency or "GBP").upper()
    company = Company(
        client_id=client.id,
        name=body.name.strip(),
        company_number=body.company_number,
        industry=body.industry,
        company_type=body.company_type or "trading",
        functional_currency=currency,
    )
    session.add(company)
    await session.flush()
    await session.refresh(company)
    return company


@router.get("/{client_id}/companies", response_model=CompanyListResponse)
async def list_companies_for_client(
    client_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CompanyListResponse:
    await aset_rls_org_id(session, auth.org_id)
    await get_owned_client(session, client_id=client_id, org_id=auth.org_id)
    result = await session.execute(
        select(Company)
        .where(
            Company.client_id == client_id,
            Company.is_deleted.is_(False),
        )
        .order_by(Company.created_at.desc())
    )
    items = list(result.scalars().all())
    return CompanyListResponse(
        client_id=client_id,
        items=[CompanyResponse.model_validate(item) for item in items],
        total=len(items),
    )


@router.get("/{client_id}/mappings", response_model=ClientGroupMappingsResponse)
async def list_client_mappings(
    client_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ClientGroupMappingsResponse:
    """Confirmed mappings across all companies under this client group."""
    await aset_rls_org_id(session, auth.org_id)
    await get_owned_client(session, client_id=client_id, org_id=auth.org_id)
    result = await session.execute(
        select(AccountMapping)
        .join(Company, Company.id == AccountMapping.company_id)
        .where(
            Company.client_id == client_id,
            Company.is_deleted.is_(False),
            AccountMapping.is_confirmed.is_(True),
        )
        .order_by(AccountMapping.source_code, AccountMapping.source_name)
    )
    mappings = list(result.scalars().all())
    return ClientGroupMappingsResponse(
        client_id=client_id,
        mappings=[MappingListItem.model_validate(row) for row in mappings],
    )


@router.delete(
    "/{client_id}/mappings",
    response_model=ClientGroupBulkDeleteMappingsResponse,
)
async def bulk_delete_client_mappings(
    client_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ClientGroupBulkDeleteMappingsResponse:
    """Bulk delete all account_mappings for every company under this client."""
    await aset_rls_org_id(session, auth.org_id)
    await get_owned_client(session, client_id=client_id, org_id=auth.org_id)
    company_ids = list(
        (
            await session.execute(
                select(Company.id).where(
                    Company.client_id == client_id,
                    Company.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    if not company_ids:
        return ClientGroupBulkDeleteMappingsResponse(client_id=client_id, deleted_count=0)
    result = await session.execute(
        delete(AccountMapping)
        .where(AccountMapping.company_id.in_(company_ids))
        .returning(AccountMapping.id)
    )
    deleted_ids = result.scalars().all()
    return ClientGroupBulkDeleteMappingsResponse(
        client_id=client_id,
        deleted_count=len(deleted_ids),
    )
