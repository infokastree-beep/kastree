"""Statutory pages that sit in front of the statement of financial position.

Python fills these from the entity record and from the profit figure the
statement engine already produced. A missing fact stays missing. This module
does not invent an approval date or attach an auditor's report. When the
audit exemption is claimed, the audit-exemption page is an explanatory note.
The statement itself is pack text printed on the balance sheet.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from app.services.statutory_display import (
    format_iso_date,
    format_whole_prose,
    parse_iso_date,
    statement_period_phrase,
)


_DIVIDEND_UNANSWERED = "[dividend not recorded]"
_DIVIDEND_NONE = "No dividend has been recorded for the financial year."
_DIVIDEND_RECORDED = "A dividend has been recorded for the financial year."
_DIVIDEND_TOLERANCE = Decimal("0.01")


@dataclass(frozen=True)
class StatutoryPage:
    heading: str
    paragraphs: tuple[str, ...]


_AUDIT_EXEMPTION_KEYS = frozenset(
    {"source", "provision", "source_status", "paragraphs", "explanatory_note"}
)
_RESEARCHED = "researched (public source)"


def audit_exemption_pack(manifest: object) -> tuple[tuple[str, ...], str]:
    """CRO statement paragraphs and the explanatory note.

    ``source_status`` is researched from a public source. It is not a
    reviewer sign-off.
    """
    if not isinstance(manifest, Mapping):
        raise ValueError("Pinned pack has no audit-exemption statements")
    block = manifest.get("audit_exemption_statements")
    if not isinstance(block, Mapping) or set(block) != _AUDIT_EXEMPTION_KEYS:
        raise ValueError("Pinned pack has no audit-exemption statements")
    provision = block.get("provision")
    paragraphs = block.get("paragraphs")
    note = block.get("explanatory_note")
    if (
        block.get("source") != "CRO"
        or block.get("source_status") != _RESEARCHED
        or not isinstance(provision, str)
        or "335" not in provision
        or not isinstance(paragraphs, list)
        or not paragraphs
        or not isinstance(note, str)
    ):
        raise ValueError(
            "Pinned pack audit-exemption statements are not researched (public source)"
        )
    cleaned: list[str] = []
    for item in paragraphs:
        if not isinstance(item, str) or not item or item != item.strip():
            raise ValueError("Pinned pack audit-exemption statements are unusable")
        cleaned.append(item)
    if not note or note != note.strip():
        raise ValueError("Pinned pack audit-exemption explanatory note is unusable")
    return (tuple(cleaned), note)


def audit_exemption_statements(manifest: object) -> tuple[str, ...]:
    """Statement printed on the balance sheet when the claim is true."""
    paragraphs, _note = audit_exemption_pack(manifest)
    return paragraphs


def audit_exemption_note(manifest: object) -> str:
    """Explanatory note. It is not the statement on the balance sheet."""
    _paragraphs, note = audit_exemption_pack(manifest)
    return note


def build_statutory_pages(
    *,
    company_name: str,
    practice_name: str,
    period_end: str,
    directors: str,
    secretary: str,
    principal_activity: str,
    currency: str,
    profit: Decimal,
    size_eligible: bool | None,
    period_start: str = "",
    approval_date: str = "",
    signing_directors: str = "",
    dividends: Decimal | None = None,
    audit_exemption_claimed: bool | None = None,
    audit_note: str = "",
) -> tuple[StatutoryPage, ...]:
    """Compilation, directors' report, approval, then audit exemption."""
    return (
        _compilation(company_name=company_name, practice_name=practice_name),
        _directors_report(
            period_end=period_end,
            period_start=period_start,
            directors=directors,
            secretary=secretary,
            principal_activity=principal_activity,
            currency=currency,
            profit=profit,
            dividends=dividends,
        ),
        _approval(
            directors=directors,
            approval_date=approval_date,
            signing_directors=signing_directors,
        ),
        _audit_exemption(
            size_eligible=size_eligible,
            claimed=audit_exemption_claimed,
            explanatory_note=audit_note,
        ),
    )


def _present(value: str) -> str:
    return value.strip()


def _compilation(*, company_name: str, practice_name: str) -> StatutoryPage:
    company = _present(company_name) or "the company (name not recorded)"
    practice = _present(practice_name)
    if practice:
        opening = (
            f"{practice} compiled these financial statements for {company} "
            "from information supplied by the directors."
        )
    else:
        opening = (
            "The practice name has not been recorded. These financial "
            f"statements for {company} were compiled from information "
            "supplied by the directors."
        )
    return StatutoryPage(
        heading="Compilation report",
        paragraphs=(
            opening + " This compilation is not an audit and it is not a review. "
            "No audit opinion and no review conclusion is expressed. "
            "The directors remain responsible for the financial statements.",
        ),
    )


def _directors_report(
    *,
    period_end: str,
    period_start: str = "",
    directors: str,
    secretary: str,
    principal_activity: str,
    currency: str,
    profit: Decimal,
    dividends: Decimal | None = None,
) -> StatutoryPage:
    end = parse_iso_date(period_end)
    start = parse_iso_date(period_start)
    if end is not None:
        period = (
            "The directors present their report "
            f"{statement_period_phrase(start, end)}."
        )
    elif _present(period_end):
        period = (
            "The directors present their report for the year ended "
            f"{_present(period_end)}."
        )
    else:
        period = "The financial year end has not been recorded."
    named = _present(directors)
    if named:
        director_line = f"The directors who served during the year are {named}."
    else:
        director_line = (
            "The directors who served during the year have not been recorded."
        )
    secretary_name = _present(secretary)
    if secretary_name:
        secretary_line = f"The company secretary is {secretary_name}."
    else:
        secretary_line = "The company secretary has not been recorded."
    activity = _present(principal_activity)
    if activity:
        activity_line = f"Principal activities: {activity}."
    else:
        activity_line = "Principal activities have not been recorded."
    if _present(currency):
        profit_line = (
            "Profit for the financial year is "
            f"{format_whole_prose(profit, currency)}."
        )
    else:
        profit_line = (
            "Profit for the financial year is "
            f"{format_whole_prose(profit, '')} "
            "(the functional currency has not been recorded)."
        )
    return StatutoryPage(
        heading="Directors' report",
        paragraphs=(
            period,
            director_line,
            secretary_line,
            activity_line,
            profit_line,
            "This is a small-company directors' report. "
            "It does not include a business review.",
            _dividend_line(dividends),
        ),
    )


def _dividend_line(dividends: Decimal | None) -> str:
    """Placeholder until the trial balance answers the dividend question.

    ``None`` means the question is unanswered. Zero means no dividend was
    recorded. Any other amount means one was. The sentence does not repeat
    the amount.
    """
    if dividends is None:
        return _DIVIDEND_UNANSWERED
    if abs(dividends) <= _DIVIDEND_TOLERANCE:
        return _DIVIDEND_NONE
    return _DIVIDEND_RECORDED


def _approval(
    *, directors: str, approval_date: str, signing_directors: str
) -> StatutoryPage:
    approved = _present(approval_date)
    if approved:
        date_line = (
            "The financial statements were approved on " f"{format_iso_date(approved)}."
        )
    else:
        date_line = "Approval date has not been recorded."
    signatories = _present(signing_directors)
    named = _present(directors)
    if signatories:
        signatory = f"The financial statements were signed by {signatories}."
    elif named:
        signatory = (
            f"The directors recorded on this draft are {named}. "
            "A signatory has not been separately recorded."
        )
    else:
        signatory = "A signatory has not been recorded."
    return StatutoryPage(
        heading="Approval of the financial statements",
        paragraphs=(date_line, signatory),
    )


def _audit_exemption(
    *,
    size_eligible: bool | None,
    claimed: bool | None = None,
    explanatory_note: str = "",
) -> StatutoryPage:
    if claimed is True:
        note = explanatory_note.strip()
        if not note:
            raise ValueError("Audit exemption explanatory note is missing")
        return StatutoryPage(heading="Audit exemption", paragraphs=(note,))
    if size_eligible is True:
        body = (
            "The recorded size test meets the pack's small-company conditions. "
            "Section 358 of the Companies Act 2014 is the non-group "
            "small-company condition. This draft does not make the statement "
            "required by section 335. The directors have not recorded that "
            "they are availing of the exemption provided for by Chapter 15 "
            "of Part 6 of the Companies Act 2014, that section 358 is "
            "complied with, or that no notice under section 334 was served."
        )
    elif size_eligible is False:
        body = (
            "This draft does not claim the audit exemption. The recorded "
            "size test does not meet the pack's small-company conditions."
        )
    else:
        body = (
            "This draft does not claim the audit exemption. "
            "The size test has not been recorded."
        )
    return StatutoryPage(heading="Audit exemption", paragraphs=(body,))
