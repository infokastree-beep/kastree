"""Statutory pages that sit in front of the statement of financial position.

Python fills these from the entity record and from the profit figure the
statement engine already produced. A missing fact stays missing. This module
does not declare a section 335 audit exemption, invent an approval date, or
attach an auditor's report.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.schemas.year_end import amount_text


@dataclass(frozen=True)
class StatutoryPage:
    heading: str
    paragraphs: tuple[str, ...]


def build_statutory_pages(
    *,
    company_name: str,
    practice_name: str,
    period_end: str,
    directors: str,
    secretary: str,
    industry: str,
    currency: str,
    profit: Decimal,
    size_eligible: bool | None,
) -> tuple[StatutoryPage, ...]:
    """Compilation, directors' report, approval, then audit exemption."""
    return (
        _compilation(company_name=company_name, practice_name=practice_name),
        _directors_report(
            period_end=period_end,
            directors=directors,
            secretary=secretary,
            industry=industry,
            currency=currency,
            profit=profit,
        ),
        _approval(directors=directors),
        _audit_exemption(size_eligible=size_eligible),
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
    directors: str,
    secretary: str,
    industry: str,
    currency: str,
    profit: Decimal,
) -> StatutoryPage:
    year = _present(period_end)
    if year:
        period = f"The directors present their report for the year ended {year}."
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
    activity = _present(industry)
    if activity:
        activity_line = f"Principal activities: {activity}."
    else:
        activity_line = "Principal activities have not been recorded."
    currency_code = _present(currency) or "the functional currency (not recorded)"
    profit_line = (
        "Profit for the financial year is " f"{currency_code} {amount_text(profit)}."
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
            "A dividend has not been recorded on this draft.",
        ),
    )


def _approval(*, directors: str) -> StatutoryPage:
    named = _present(directors)
    if named:
        signatory = (
            f"The directors recorded on this draft are {named}. "
            "A signatory has not been separately recorded."
        )
    else:
        signatory = "A signatory has not been recorded."
    return StatutoryPage(
        heading="Approval of the financial statements",
        paragraphs=("Approval date has not been recorded.", signatory),
    )


def _audit_exemption(*, size_eligible: bool | None) -> StatutoryPage:
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
