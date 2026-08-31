"""Shared ownership helpers for client/company resources under RLS."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.company import Company


async def get_owned_client(
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


async def get_owned_company(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    org_id: uuid.UUID,
    include_deleted: bool = False,
) -> Company:
    """Resolve company via client org; 404 when cross-org or soft-deleted."""
    clauses = [
        Company.id == company_id,
        Client.org_id == org_id,
        Client.is_deleted.is_(False),
    ]
    if not include_deleted:
        clauses.append(Company.is_deleted.is_(False))
    result = await session.execute(
        select(Company)
        .join(Client, Client.id == Company.client_id)
        .where(*clauses)
    )
    company = result.scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company
