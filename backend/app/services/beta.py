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
from typing import Literal, NamedTuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.audit_log import AuditLog
from app.models.organisation import Organisation
from app.services.audit import append_audit_log

PACK_ID: Literal["frs102-1a-ie"] = "frs102-1a-ie"
BETA_ACTION = "beta_self_review"
PRODUCT2_ACCESS_GRANTED = "product2_access_granted"
PRODUCT2_ACCESS_REVOKED = "product2_access_revoked"

# A qualified reviewer has not signed this wording off. Documents and
# /users/me read this value. The client does not decide it.
WORDING_SIGNED_OFF: bool = False
WORDING_BANNER = "Statutory wording not yet reviewed by a qualified reviewer"


class FinalPagePresentation(NamedTuple):
    wording_signed_off: bool
    page_label: str
    wording_banner: str
    printed_header: str


def final_page_presentation(status_header: str) -> FinalPagePresentation:
    """Decide the header a page prints.

    A header that is not FINAL is unchanged. When a qualified reviewer has
    signed the wording off, FINAL prints as FINAL. Otherwise FINAL prints as
    DRAFT followed by the wording banner. The document status stays FINAL.
    """
    signed = WORDING_SIGNED_OFF
    header = status_header.strip()
    if signed or not (header == "FINAL" or header.startswith("FINAL ")):
        return FinalPagePresentation(signed, header, "", header)
    rest = header[len("FINAL") :].strip()
    page_label = "DRAFT" if rest == "" else f"DRAFT {rest}"
    printed = f"{page_label} {WORDING_BANNER}"
    return FinalPagePresentation(False, page_label, WORDING_BANNER, printed)


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


async def product2_grant_source(
    session: AsyncSession, *, org_id: uuid.UUID
) -> Literal["practice", "admin"] | None:
    """Latest acknowledgement audit source, or none when it is not practice or admin."""
    await aset_rls_org_id(session, org_id)
    raw = await session.scalar(
        select(AuditLog.new_value["source"].as_string())
        .where(
            AuditLog.org_id == org_id,
            AuditLog.action.in_((BETA_ACTION, PRODUCT2_ACCESS_GRANTED)),
        )
        .order_by(AuditLog.chain_seq.desc())
        .limit(1)
    )
    if raw == "practice":
        return "practice"
    if raw == "admin":
        return "admin"
    return None


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


async def set_product2_access(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    acknowledged: bool,
) -> bool | None:
    """Turn Product 2 on or off for one practice.

    ``app.current_org_id`` is set to that practice for this transaction only.
    The statement writes the two acknowledgement columns and one audit row.
    It does not write subscription, Stripe, currency, or jurisdiction.
    A practice acknowledgement cannot clear the columns; only this call can.
    A second grant or a second revoke records nothing. None means the
    practice does not exist.
    """
    await aset_rls_org_id(session, org_id)
    practice = await session.get(Organisation, org_id, with_for_update=True)
    if practice is None:
        return None
    already = practice.product2_acknowledged_at is not None
    if acknowledged == already:
        return False
    if acknowledged:
        await session.execute(
            text(
                """
                UPDATE organisations
                SET product2_acknowledged_at = :at,
                    product2_acknowledged_by_user_id = :by
                WHERE id = :id
                """
            ),
            {
                "at": datetime.now(UTC),
                "by": str(actor_user_id),
                "id": str(org_id),
            },
        )
        session.expire(practice)
        await append_audit_log(
            session,
            org_id=org_id,
            user_id=actor_user_id,
            action=PRODUCT2_ACCESS_GRANTED,
            entity_type="organisation",
            entity_id=org_id,
            old_value=None,
            new_value={"source": "admin"},
        )
        return True
    acknowledged_at = practice.product2_acknowledged_at
    acknowledged_by = practice.product2_acknowledged_by_user_id
    old_value: dict[str, object] = {
        "product2_acknowledged_at": (
            None if acknowledged_at is None else acknowledged_at.isoformat()
        ),
        "product2_acknowledged_by_user_id": (
            None if acknowledged_by is None else str(acknowledged_by)
        ),
    }
    await session.execute(
        text(
            """
            UPDATE organisations
            SET product2_acknowledged_at = NULL,
                product2_acknowledged_by_user_id = NULL
            WHERE id = :id
            """
        ),
        {"id": str(org_id)},
    )
    session.expire(practice)
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=actor_user_id,
        action=PRODUCT2_ACCESS_REVOKED,
        entity_type="organisation",
        entity_id=org_id,
        old_value=old_value,
        new_value=None,
    )
    return True
