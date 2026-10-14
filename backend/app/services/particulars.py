"""Preparer particulars for the notes. Python does not calculate them.

A Yes answer with an empty slot blocks FINAL. A No or an unanswered
question does not. The wording is researched from the public Act. It is
not a reviewer sign-off.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.schemas.company_details import ParticularsWrite
from app.services.audit import append_audit_log
from app.services.company_details import (
    CompanyDetailsRejected,
    _share_class_audit,
    _share_classes,
)
from app.services.directors_report import DirectorsReportRejected, _blank, _prose
from app.services.reconciliation import ReconciliationCheck
from findraft.models.year_end import YearEnd

_TEXT = {
    "related_party_particulars": "Related party particulars",
    "directors_remuneration_particulars": "Directors' remuneration particulars",
    "loan_terms_particulars": "Loans and credit particulars",
    "guarantee_particulars": "Guarantee particulars",
    "subsequent_events_particulars": "Subsequent events particulars",
}


def particulars_checks(
    year_end: YearEnd,
    flags: Mapping[str, bool] | None,
) -> tuple[ReconciliationCheck, ...]:
    """Only a Yes with an empty slot is a check. Other answers stay quiet."""
    if not flags:
        return ()
    checks: list[ReconciliationCheck] = []
    if flags.get("RPT_EXISTS") is True:
        checks.append(
            _slot(
                "V-CO-040",
                year_end.related_party_particulars,
                "Related party particulars are recorded.",
                "Related party particulars have not been recorded.",
            )
        )
    if flags.get("DIRECTORS_EXIST") is True:
        checks.append(
            _slot(
                "V-CO-041",
                year_end.directors_remuneration_particulars,
                "Directors' remuneration particulars are recorded.",
                (
                    "Directors' remuneration particulars have not been recorded. "
                    "Companies Act 2014, sections 305 and 306."
                ),
            )
        )
    if (
        flags.get("CONNECTED_LOANS") is True
        or flags.get("DIRECTOR_LOAN_AGREEMENTS") is True
    ):
        checks.append(
            _slot(
                "V-CO-042",
                year_end.loan_terms_particulars,
                "Loans and credit particulars are recorded.",
                (
                    "Loans and credit particulars have not been recorded. "
                    "Companies Act 2014, sections 307 and 308."
                ),
            )
        )
    if (
        flags.get("GUARANTEES_EXIST") is True
        or flags.get("DIRECTOR_GUARANTEES") is True
        or flags.get("DIRECTOR_GUARANTEE_AGREEMENTS") is True
    ):
        checks.append(
            _slot(
                "V-CO-043",
                year_end.guarantee_particulars,
                "Guarantee particulars are recorded.",
                "Guarantee particulars have not been recorded.",
            )
        )
    return tuple(checks)


async def save_particulars(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    company: Company,
    year_end: YearEnd,
    body: ParticularsWrite,
) -> None:
    """Store the typed slots and the share classes. The audit row omits the prose."""
    previous = _audit(year_end, company)
    year_end.related_party_particulars = _stored(
        body.related_party_particulars, "related_party_particulars"
    )
    year_end.directors_remuneration_particulars = _stored(
        body.directors_remuneration_particulars, "directors_remuneration_particulars"
    )
    year_end.loan_terms_particulars = _stored(
        body.loan_terms_particulars, "loan_terms_particulars"
    )
    year_end.guarantee_particulars = _stored(
        body.guarantee_particulars, "guarantee_particulars"
    )
    year_end.subsequent_events_particulars = _stored(
        body.subsequent_events_particulars, "subsequent_events_particulars"
    )
    company.share_classes = _share_classes(body.share_classes)
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="particulars_saved",
        entity_type="year_end",
        entity_id=year_end.id,
        old_value=previous,
        new_value=_audit(year_end, company),
    )


def _stored(value: str | None, key: str) -> str | None:
    try:
        return _prose(value, label=_TEXT[key])
    except DirectorsReportRejected as exc:
        raise CompanyDetailsRejected(exc.detail) from exc


def _slot(code: str, value: str | None, done: str, missing: str) -> ReconciliationCheck:
    recorded = _blank(value) is not None
    return ReconciliationCheck(
        code=code,
        severity="WARNING",
        passed=recorded,
        message=done if recorded else missing,
    )


def _audit(year_end: YearEnd, company: Company) -> dict[str, object]:
    return {
        "related_party_recorded": _blank(year_end.related_party_particulars) is not None,
        "directors_remuneration_recorded": _blank(
            year_end.directors_remuneration_particulars
        )
        is not None,
        "loan_terms_recorded": _blank(year_end.loan_terms_particulars) is not None,
        "guarantee_recorded": _blank(year_end.guarantee_particulars) is not None,
        "subsequent_events_recorded": _blank(year_end.subsequent_events_particulars)
        is not None,
        "share_classes": _share_class_audit(company.share_classes),
    }
