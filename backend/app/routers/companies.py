"""Companies API — manage a single company (entity under a client group)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import AuthContext, get_auth_context, get_db_session
from app.models.account_mapping import AccountMapping
from app.models.company import Company
from app.schemas.company import (
    BulkDeleteMappingsResponse,
    CompanyMappingsResponse,
    CompanyResponse,
    CompanyUpdateRequest,
    MappingListItem,
)
from app.services.archival import archive_company_user_deleted
from app.services.ownership import get_owned_company
from app.schemas.materiality import MaterialitySuggestionDismissResponse

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Company:
    await aset_rls_org_id(session, auth.org_id)
    return await get_owned_company(session, company_id=company_id, org_id=auth.org_id)


@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdateRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Company:
    await aset_rls_org_id(session, auth.org_id)
    company = await get_owned_company(session, company_id=company_id, org_id=auth.org_id)
    updates = body.model_dump(exclude_unset=True)
    if "functional_currency" in updates and updates["functional_currency"] is not None:
        updates["functional_currency"] = updates["functional_currency"].upper()
    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()
    # Changing company type resurfaces the materiality suggestion banner.
    if "company_type" in updates and updates["company_type"] != company.company_type:
        company.materiality_suggestion_dismissed_at = None
    # Applying new thresholds clears dismiss so a later drift can prompt again.
    if (
        "materiality_threshold_pct" in updates
        or "materiality_threshold_abs" in updates
    ):
        company.materiality_suggestion_dismissed_at = None
    for field, value in updates.items():
        setattr(company, field, value)
    await session.flush()
    await session.refresh(company)
    return company


@router.post(
    "/{company_id}/materiality-suggestion/dismiss",
    response_model=MaterialitySuggestionDismissResponse,
)
async def dismiss_materiality_suggestion(
    company_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialitySuggestionDismissResponse:
    """Soft-dismiss the materiality suggestion banner for this company."""
    await aset_rls_org_id(session, auth.org_id)
    company = await get_owned_company(session, company_id=company_id, org_id=auth.org_id)
    now = datetime.now(timezone.utc)
    company.materiality_suggestion_dismissed_at = now
    await session.flush()
    await session.refresh(company)
    assert company.materiality_suggestion_dismissed_at is not None
    return MaterialitySuggestionDismissResponse(
        company_id=company.id,
        materiality_suggestion_dismissed_at=company.materiality_suggestion_dismissed_at.isoformat(),
    )


@router.delete("/{company_id}", status_code=status.HTTP_200_OK, response_model=CompanyResponse)
async def soft_delete_company(
    company_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Company:
    """Soft delete + archived_records snapshot in the same transaction (§12.2)."""
    await aset_rls_org_id(session, auth.org_id)
    company = await get_owned_company(session, company_id=company_id, org_id=auth.org_id)
    now = datetime.now(timezone.utc)
    company.is_deleted = True
    company.deleted_at = now
    await session.flush()
    await session.refresh(company)
    await archive_company_user_deleted(
        session,
        company=company,
        org_id=auth.org_id,
        archived_by_user_id=auth.user_id,
        archived_at=now,
    )
    return company


@router.get("/{company_id}/mappings", response_model=CompanyMappingsResponse)
async def list_company_mappings(
    company_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CompanyMappingsResponse:
    await aset_rls_org_id(session, auth.org_id)
    await get_owned_company(session, company_id=company_id, org_id=auth.org_id)
    result = await session.execute(
        select(AccountMapping)
        .where(
            AccountMapping.company_id == company_id,
            AccountMapping.is_confirmed.is_(True),
        )
        .order_by(AccountMapping.source_code, AccountMapping.source_name)
    )
    mappings = list(result.scalars().all())
    return CompanyMappingsResponse(
        company_id=company_id,
        mappings=[MappingListItem.model_validate(row) for row in mappings],
    )


@router.delete(
    "/{company_id}/mappings",
    response_model=BulkDeleteMappingsResponse,
)
async def bulk_delete_company_mappings(
    company_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BulkDeleteMappingsResponse:
    await aset_rls_org_id(session, auth.org_id)
    await get_owned_company(session, company_id=company_id, org_id=auth.org_id)
    result = await session.execute(
        delete(AccountMapping)
        .where(AccountMapping.company_id == company_id)
        .returning(AccountMapping.id)
    )
    deleted_ids = result.scalars().all()
    return BulkDeleteMappingsResponse(
        company_id=company_id,
        deleted_count=len(deleted_ids),
    )
