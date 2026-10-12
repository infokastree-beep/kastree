"""Values a final draft shows. They come from the snapshot, not later edits.

A draft finalised before this block existed has the printed claim only inside
the composed document. Size, confirmations, and letterhead were not copied.
Those fields stay on the year-end row. The workspace does not read them back
onto a final draft.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.schemas.company_details import CompanyDetailsResponse
from app.schemas.year_end import (
    SizeEligibilityResponse,
    YearEndResponse,
    size_amount_text,
)
from app.services.company_details import company_details_response
from findraft.models.draft_version import DraftVersion
from findraft.models.year_end import YearEnd

_PRINTED_CLAIM = "(a) the company is availing itself"

_LEGACY_AUDIT_KEYS = (
    "audit_exemption_claimed",
    "audit_exemption_claimed_by_user_id",
    "audit_exemption_claimed_at",
    "audit_exemption_not_excluded",
    "audit_exemption_no_member_notice",
    "audit_exemption_returns_not_late",
    "audit_exemption_conditions_by_user_id",
    "audit_exemption_conditions_at",
    "size_current_turnover",
    "size_current_balance_sheet",
    "size_current_employees",
    "size_preceding_turnover",
    "size_preceding_balance_sheet",
    "size_preceding_employees",
    "size_message",
)


def workspace_snapshot(year_end: YearEnd, company: Company | None) -> dict[str, object]:
    """Letterhead, display settings, and the audit position as finalised."""
    details: dict[str, object] | None = None
    if (
        company is not None
        and company.org_id == year_end.org_id
        and not company.is_deleted
    ):
        details = company_details_response(company, year_end).model_dump(mode="json")
    setup = year_end.report_setup
    copied_setup: dict[str, object] | None = None
    if isinstance(setup, dict):
        raw = json.loads(json.dumps(setup))
        if isinstance(raw, dict):
            copied_setup = {str(key): value for key, value in raw.items()}
    recorded = YearEndResponse.model_validate(year_end).model_dump(mode="json")
    checked = year_end.size_checked_at
    return {
        "year_end": recorded,
        "company_details": details,
        "report_setup": copied_setup,
        "size": {
            "checked_at": None if checked is None else checked.isoformat(),
            "eligible": year_end.size_eligible,
            "current_met": year_end.size_current_met,
            "preceding_met": year_end.size_preceding_met,
            "message": year_end.size_message,
            "current_turnover": size_amount_text(year_end.size_current_turnover),
            "current_balance_sheet": size_amount_text(
                year_end.size_current_balance_sheet
            ),
            "current_employees": year_end.size_current_employees,
            "preceding_turnover": size_amount_text(year_end.size_preceding_turnover),
            "preceding_balance_sheet": size_amount_text(
                year_end.size_preceding_balance_sheet
            ),
            "preceding_employees": year_end.size_preceding_employees,
        },
    }


def display_workspace(snapshot: dict[str, object]) -> dict[str, object]:
    """Snapshot block, or the claim that was actually printed."""
    stored = snapshot.get("workspace")
    if isinstance(stored, dict):
        return {str(key): value for key, value in stored.items()}
    html = snapshot.get("composed_html")
    claimed: bool | None = (
        True if isinstance(html, str) and _PRINTED_CLAIM in html else None
    )
    legacy: dict[str, object] = {key: None for key in _LEGACY_AUDIT_KEYS}
    legacy["audit_exemption_claimed"] = claimed
    return legacy


def overlay_year_end(
    payload: dict[str, Any], view: dict[str, object]
) -> dict[str, Any]:
    """Replace year-end fields the snapshot recorded. Leave the rest."""
    recorded = view.get("year_end")
    if isinstance(recorded, dict):
        merged = dict(payload)
        merged.update(recorded)
        return merged
    merged = dict(payload)
    for key in _LEGACY_AUDIT_KEYS:
        if key in view:
            merged[key] = view[key]
    return merged


async def latest_final_snapshot(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
) -> dict[str, object] | None:
    """The latest draft's snapshot, once that draft is final."""
    draft = (
        await session.scalars(
            select(DraftVersion)
            .where(
                DraftVersion.org_id == org_id,
                DraftVersion.year_end_id == year_end.id,
            )
            .order_by(DraftVersion.version_number.desc())
            .limit(1)
        )
    ).first()
    if draft is None or draft.status != "final" or not isinstance(draft.snapshot, dict):
        return None
    return draft.snapshot


def size_from_workspace(
    view: dict[str, object], *, year_end_id: uuid.UUID
) -> SizeEligibilityResponse | None:
    """Size test copied at finalise. None when that test was not recorded."""
    raw = view.get("size")
    if not isinstance(raw, dict):
        return None
    checked = raw.get("checked_at")
    eligible = raw.get("eligible")
    current_met = raw.get("current_met")
    message = raw.get("message")
    if not isinstance(checked, str) or checked == "":
        return None
    if not isinstance(eligible, bool) or not isinstance(current_met, int):
        return None
    if not isinstance(message, str):
        return None
    preceding = raw.get("preceding_met")
    employees = raw.get("current_employees")
    preceding_employees = raw.get("preceding_employees")
    return SizeEligibilityResponse(
        year_end_id=year_end_id,
        eligible=eligible,
        current_conditions_met=current_met,
        preceding_conditions_met=preceding if isinstance(preceding, int) else None,
        message=message,
        size_current_turnover=_amount(raw.get("current_turnover")),
        size_current_balance_sheet=_amount(raw.get("current_balance_sheet")),
        size_current_employees=employees if isinstance(employees, int) else None,
        size_preceding_turnover=_amount(raw.get("preceding_turnover")),
        size_preceding_balance_sheet=_amount(raw.get("preceding_balance_sheet")),
        size_preceding_employees=(
            preceding_employees if isinstance(preceding_employees, int) else None
        ),
    )


def _amount(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return None


def company_details_from_workspace(
    view: dict[str, object],
) -> CompanyDetailsResponse | None:
    """Letterhead copied at finalise. Absent on an older snapshot."""
    details = view.get("company_details")
    if not isinstance(details, dict):
        return None
    return CompanyDetailsResponse.model_validate(details)
