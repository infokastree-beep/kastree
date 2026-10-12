"""Record an evidenced audit exemption so an existing finalise fixture can proceed.

The product blocks FINAL until the exemption is claimed, the size test
is recorded as met, and the three directors' confirmations are true.
These fixtures are not the fictional company.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id

_MESSAGE = "Current year: turnover met; balance sheet total met; employees met."


def record_evidenced_exemption(org_id: uuid.UUID, year_end_id: str) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                """
                UPDATE findraft_year_ends
                SET audit_exemption_claimed = TRUE,
                    audit_exemption_claimed_at = NOW(),
                    audit_exemption_not_excluded = TRUE,
                    audit_exemption_no_member_notice = TRUE,
                    audit_exemption_returns_not_late = TRUE,
                    audit_exemption_conditions_at = NOW(),
                    size_eligible = TRUE,
                    size_checked_at = NOW(),
                    size_current_met = 3,
                    size_preceding_met = NULL,
                    size_message = :message
                WHERE id = :id
                """
            ),
            {"id": year_end_id, "message": _MESSAGE},
        )
        session.commit()
