"""Framework catalogue and report-setup display settings.

The statement engine does not import this module. Saving these fields does
not rebuild a draft, and display rounding returns a new string.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.report_setup import (
    ColumnHeaders,
    FaceDates,
    ReportingFrameworkList,
    ReportingFrameworkOut,
    ReportSetupResponse,
    ReportSetupWrite,
    WorkspaceSectionOut,
)
from app.services.audit import append_audit_log
from findraft.models.year_end import YearEnd


@dataclass(frozen=True)
class WorkspaceSection:
    id: str
    label: str
    group: str
    group_label: str
    order: int


@dataclass(frozen=True)
class ReportingFramework:
    id: str
    version: str
    label: str
    available: bool
    sections: tuple[WorkspaceSection, ...]


_FRS_SECTIONS: tuple[WorkspaceSection, ...] = (
    WorkspaceSection("review", "Review dashboard", "overview", "Overview", 1),
    WorkspaceSection("report-setup", "Report setup", "report-options", "Report options", 2),
    WorkspaceSection("sub-lines", "Mapping", "inputs", "Inputs", 3),
    WorkspaceSection("adjustments", "Adjustments", "inputs", "Inputs", 4),
    WorkspaceSection("disclosures", "Disclosures", "inputs", "Inputs", 5),
    WorkspaceSection("company-details", "Company details", "inputs", "Inputs", 6),
    WorkspaceSection("income", "Income statement", "sections", "Sections", 7),
    WorkspaceSection("sofp", "Statement of financial position", "sections", "Sections", 8),
)

_FORM11_SECTIONS: tuple[WorkspaceSection, ...] = (
    WorkspaceSection("review", "Review dashboard", "overview", "Overview", 1),
    WorkspaceSection("report-setup", "Report setup", "report-options", "Report options", 2),
)

_FALLBACK_SECTIONS: tuple[WorkspaceSection, ...] = (
    WorkspaceSection("review", "Review dashboard", "overview", "Overview", 1),
    WorkspaceSection("report-setup", "Report setup", "report-options", "Report options", 2),
)

REPORTING_FRAMEWORKS: tuple[ReportingFramework, ...] = (
    ReportingFramework(
        id="frs102-1a-ie",
        version="2024.09",
        label="FRS 102 Section 1A (Ireland)",
        available=True,
        sections=_FRS_SECTIONS,
    ),
    ReportingFramework(
        id="form11-summary",
        version="2025",
        label="Sole Trader / Form 11 Summary",
        available=False,
        sections=_FORM11_SECTIONS,
    ),
)


def sections_for(framework_id: str) -> tuple[WorkspaceSection, ...]:
    """Sidebar entries for one framework. An unknown id is not the FRS list."""
    for framework in REPORTING_FRAMEWORKS:
        if framework.id == framework_id:
            return framework.sections
    return _FALLBACK_SECTIONS


def framework_label(framework_id: str, version: str) -> str:
    for framework in REPORTING_FRAMEWORKS:
        if framework.id == framework_id and framework.version == version:
            return framework.label
    return framework_id


def framework_list() -> ReportingFrameworkList:
    return ReportingFrameworkList(
        frameworks=[
            ReportingFrameworkOut(
                id=framework.id,
                version=framework.version,
                label=framework.label,
                available=framework.available,
                sections=[
                    WorkspaceSectionOut(
                        id=section.id,
                        label=section.label,
                        group=section.group,
                        group_label=section.group_label,
                        order=section.order,
                    )
                    for section in framework.sections
                ],
            )
            for framework in REPORTING_FRAMEWORKS
        ]
    )


def display_amount(amount: Decimal, rounding: str) -> str:
    """A new display string. ``amount`` is left as it was passed in."""
    if rounding == "thousands":
        shown = (amount / Decimal("1000")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    else:
        shown = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return format(shown, "f")


def default_report_setup(year_end: YearEnd) -> ReportSetupWrite:
    """Words that match the year end until the practice saves its own."""
    current_year = str(year_end.period_end.year)
    prior_year = str(year_end.period_end.year - 1)
    return ReportSetupWrite(
        rounding="unit",
        statement_type="draft",
        face_dates=FaceDates(
            current_start=year_end.period_start,
            current_end=year_end.period_end,
            prior_start=None,
            prior_end=None,
        ),
        column_headers=ColumnHeaders(
            as_at_current=current_year,
            as_at_prior=prior_year,
            ended_current=current_year,
            ended_prior=prior_year,
        ),
    )


def _stored_setup(year_end: YearEnd) -> ReportSetupWrite:
    raw = year_end.report_setup
    if raw is None:
        return default_report_setup(year_end)
    return ReportSetupWrite.model_validate(raw)


def report_setup_response(year_end: YearEnd) -> ReportSetupResponse:
    setup = _stored_setup(year_end)
    return ReportSetupResponse(
        basis_id=year_end.pack_id,
        basis_version=year_end.pack_version,
        basis_label=framework_label(year_end.pack_id, year_end.pack_version),
        rounding=setup.rounding,
        statement_type=setup.statement_type,
        face_dates=setup.face_dates,
        column_headers=setup.column_headers,
        trial_balance_period_start=year_end.period_start,
        trial_balance_period_end=year_end.period_end,
    )


async def save_report_setup(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    year_end: YearEnd,
    body: ReportSetupWrite,
) -> ReportSetupResponse:
    """Replace display settings. Period columns and the pack pin stay put."""
    previous = year_end.report_setup
    stored = body.model_dump(mode="json")
    year_end.report_setup = stored
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="report_setup_saved",
        entity_type="year_end",
        entity_id=year_end.id,
        old_value=previous if isinstance(previous, dict) else None,
        new_value=stored,
    )
    return report_setup_response(year_end)
