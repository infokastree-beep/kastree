"""First-practice beta position.

A qualified reviewer has not signed off the statutory wording. The practice
records that it will review every output itself. The record is one audit row.
This module does not file, and it does not claim the golden suite has run.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.audit_log import AuditLog
from app.services.audit import append_audit_log

PACK_ID: Literal["frs102-1a-ie"] = "frs102-1a-ie"
BETA_ACTION = "beta_self_review"

BETA_STATEMENT = (
    "This is the first-practice beta of the Irish FRS 102 Section 1A "
    "members' accounts draft on pack frs102-1a-ie. A qualified reviewer has "
    "not signed off the statutory wording. The practice reviews every output "
    "itself before anything is filed or sent. This product does not file. "
    "It does not produce iXBRL or a CT1. The numeric acceptance gate is the "
    "engine golden suite. Roll-forward and report styles are not in this beta."
)


async def beta_acknowledged(session: AsyncSession, *, org_id: uuid.UUID) -> bool:
    await aset_rls_org_id(session, org_id)
    found = await session.scalar(
        select(AuditLog.id)
        .where(AuditLog.org_id == org_id, AuditLog.action == BETA_ACTION)
        .limit(1)
    )
    return found is not None


async def acknowledge_beta_self_review(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> bool:
    """Append one audit row. A second call records nothing."""
    await aset_rls_org_id(session, org_id)
    await session.execute(
        text("SELECT id FROM organisations WHERE id = :id FOR UPDATE"),
        {"id": str(org_id)},
    )
    if await beta_acknowledged(session, org_id=org_id):
        return False
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=actor_user_id,
        action=BETA_ACTION,
        entity_type="organisation",
        entity_id=org_id,
        old_value=None,
        new_value={
            "wording_signed_off": False,
            "self_review_required": True,
            "filing_included": False,
            "pack_id": PACK_ID,
        },
    )
    return True
