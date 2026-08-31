"""Immutable archival helpers (Product Spec §9.1 / §12.2).

Writes append-only archived_records rows with a SHA-256 of the JSON snapshot.
Only the clients soft-delete path is wired in this slice; trial_balances and
financial_statements still lack an archival WRITE path (see router docstring).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.archived_record import ArchivedRecord
from app.models.client import Client
from app.models.company import Company

RETENTION_YEARS = 7


def add_years(value: date, years: int) -> date:
    """Calendar +years, clamping Feb 29 → Feb 28 when needed."""
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, month=2, day=28)


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Stable JSON encoding for hashing (sorted keys, compact separators).

    sort_keys=True makes the digest independent of dict insertion order so the
    same client snapshot always yields the same SHA-256 (§12.2 tamper-evidence).
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def sha256_hex(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def verify_archive_hash(archived_data: dict[str, Any], archive_hash: str) -> bool:
    """Recompute SHA-256 of archived_data and compare to stored archive_hash (§10.2)."""
    return sha256_hex(archived_data) == archive_hash


def client_snapshot(client: Client) -> dict[str, Any]:
    """Full clients-row snapshot for archived_data."""
    return {
        "id": str(client.id),
        "org_id": str(client.org_id),
        "name": client.name,
        "is_deleted": client.is_deleted,
        "deleted_at": client.deleted_at.isoformat() if client.deleted_at else None,
        "created_at": client.created_at.isoformat() if client.created_at else None,
        "updated_at": client.updated_at.isoformat() if client.updated_at else None,
    }


def company_snapshot(company: Company) -> dict[str, Any]:
    """Full companies-row snapshot for archived_data."""
    return {
        "id": str(company.id),
        "client_id": str(company.client_id),
        "name": company.name,
        "company_number": company.company_number,
        "industry": company.industry,
        "functional_currency": company.functional_currency,
        "materiality_threshold_pct": str(company.materiality_threshold_pct),
        "materiality_threshold_abs": str(company.materiality_threshold_abs),
        "is_deleted": company.is_deleted,
        "deleted_at": company.deleted_at.isoformat() if company.deleted_at else None,
        "created_at": company.created_at.isoformat() if company.created_at else None,
        "updated_at": company.updated_at.isoformat() if company.updated_at else None,
    }


async def archive_client_user_deleted(
    session: AsyncSession,
    *,
    client: Client,
    archived_by_user_id: uuid.UUID,
    archived_at: datetime | None = None,
) -> ArchivedRecord:
    """Append archived_records row for a user soft-deleted client (same txn)."""
    when = archived_at or datetime.now(timezone.utc)
    snapshot = client_snapshot(client)
    record = ArchivedRecord(
        org_id=client.org_id,
        client_id=client.id,
        entity_type="client",
        entity_id=client.id,
        archive_reason="user_deleted",
        archived_by_user_id=archived_by_user_id,
        archived_data=snapshot,
        archive_hash=sha256_hex(snapshot),
        retention_until=add_years(when.date(), RETENTION_YEARS),
    )
    session.add(record)
    await session.flush()
    return record


async def archive_company_user_deleted(
    session: AsyncSession,
    *,
    company: Company,
    org_id: uuid.UUID,
    archived_by_user_id: uuid.UUID,
    archived_at: datetime | None = None,
) -> ArchivedRecord:
    """Append archived_records row for a user soft-deleted company (same txn)."""
    when = archived_at or datetime.now(timezone.utc)
    snapshot = company_snapshot(company)
    record = ArchivedRecord(
        org_id=org_id,
        client_id=company.client_id,
        entity_type="company",
        entity_id=company.id,
        archive_reason="user_deleted",
        archived_by_user_id=archived_by_user_id,
        archived_data=snapshot,
        archive_hash=sha256_hex(snapshot),
        retention_until=add_years(when.date(), RETENTION_YEARS),
    )
    session.add(record)
    await session.flush()
    return record
