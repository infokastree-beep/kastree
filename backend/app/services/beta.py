"""First-practice beta position.

A qualified reviewer has not signed off the statutory wording. The practice
records that it will review every output itself. The current state is the
acknowledgement columns on the organisation. Each recording also appends one
audit row. This module does not file, and it does not claim the golden suite
has run.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.organisation import Organisation
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
    """True when this practice's acknowledgement columns are set.

    An old ``beta_self_review`` audit row is history. It does not keep the
    practice on after the columns are cleared.
    """
    await aset_rls_org_id(session, org_id)
    acknowledged_at = await session.scalar(
        select(Organisation.product2_acknowledged_at).where(Organisation.id == org_id)
    )
    return acknowledged_at is not None


async def acknowledge_beta_self_review(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> bool:
    """Set the practice columns and append one audit row.

    A second call while the columns are set records nothing. Clearing the
    columns allows another acknowledgement, which appends a new audit row.
    """
    await aset_rls_org_id(session, org_id)
    await session.execute(
        text("SELECT id FROM organisations WHERE id = :id FOR UPDATE"),
        {"id": str(org_id)},
    )
    practice = await session.get(Organisation, org_id)
    if practice is None or practice.product2_acknowledged_at is not None:
        return False
    practice.product2_acknowledged_at = datetime.now(UTC)
    practice.product2_acknowledged_by_user_id = actor_user_id
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
            "source": "practice",
        },
    )
    return True
