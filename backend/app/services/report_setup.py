"""Framework catalogue and report-setup display settings.

The statement engine does not import this module. Saving these fields does
not rebuild a draft, and display rounding returns a new string.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.report_setup import (
    ColumnHeaders,
    FaceDates,
    ReportingFrameworkList,
    ReportingFrameworkOut,
    ReportSetupResponse,
    ReportSetupWrite,
    WorkspaceSectionOut,
    pack_section_catalogue,
)
from app.services.audit import append_audit_log
from app.services.statutory_display import column_headings, rounding_labels
from findraft.engine.pack import load_manifest
from findraft.models.year_end import YearEnd


@dataclass(frozen=True)
class WorkspaceSection:
    id: str
    label: str
    group: str
    group_label: str
    order: int
    lock: str | None = None
    default: str | None = None
    built: bool | None = None
    children: str | None = None


@dataclass(frozen=True)
class ReportingFramework:
    id: str
    version: str
    label: str
    available: bool
    sections: tuple[WorkspaceSection, ...]


_WORKSPACE_BEFORE: tuple[WorkspaceSection, ...] = (
    WorkspaceSection("review", "Review dashboard", "overview", "Overview", 1),
    WorkspaceSection(
        "report-setup", "Report setup", "report-options", "Report options", 2
    ),
    WorkspaceSection("sub-lines", "Mapping", "inputs", "Inputs", 3),
    WorkspaceSection("adjustments", "Adjustments", "inputs", "Inputs", 4),
    WorkspaceSection("disclosures", "Disclosures", "inputs", "Inputs", 5),
    WorkspaceSection("company-details", "Company details", "inputs", "Inputs", 6),
)


def _built_flag(item: dict[str, object]) -> bool:
    """Missing means the pack builds the section. ``false`` is the not-built tag."""
    if "built" not in item:
        return True
    raw = item["built"]
    if not isinstance(raw, bool):
        raise ValueError("pack section built is malformed")
    return raw


def section_children_marker(item: dict[str, object]) -> str | None:
    """Pack tree marker. ``printed-notes`` expands from the composed notes."""
    if "children" not in item:
        return None
    raw = item["children"]
    if raw == "printed-notes":
        return "printed-notes"
    if isinstance(raw, list):
        for child in raw:
            if not isinstance(child, dict):
                raise ValueError("pack section children are malformed")
            child_id = child.get("id")
            label = child.get("label")
            if not isinstance(child_id, str) or not child_id:
                raise ValueError("pack section children are malformed")
            if not isinstance(label, str) or not label:
                raise ValueError("pack section children are malformed")
        return "declared" if raw else None
    raise ValueError("pack section children are malformed")


def _pack_sidebar() -> tuple[WorkspaceSection, ...]:
    """Pack order, then the Outputs group. Labels come from the pack file."""
    catalogue = pack_section_catalogue()
    loaded: object = load_manifest()
    if not isinstance(loaded, dict):
        raise ValueError("pack manifest is malformed")
    raw = loaded.get("sections")
    if not isinstance(raw, list):
        raise ValueError("pack sections are missing")
    rows: list[WorkspaceSection] = [
        WorkspaceSection(
            id="sections-setup",
            label="Sections setup",
            group="sections",
            group_label="Sections",
            order=len(_WORKSPACE_BEFORE) + 1,
        )
    ]
    order = len(_WORKSPACE_BEFORE) + 2
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("pack section is malformed")
        section_id = item.get("id")
        if not isinstance(section_id, str) or section_id not in catalogue:
            raise ValueError("pack section id is malformed")
        rule = catalogue[section_id]
        rows.append(
            WorkspaceSection(
                id=section_id,
                label=rule["label"],
                group="sections",
                group_label="Sections",
                order=order,
                lock=rule["lock"],
                default=rule["default"],
                built=_built_flag(item),
                children=section_children_marker(item),
            )
        )
        order += 1
    rows.append(
        WorkspaceSection(
            id="draft-pdf",
            label="Draft PDF",
            group="outputs",
            group_label="Outputs",
            order=order,
        )
    )
    return tuple(rows)


def _frs_sections() -> tuple[WorkspaceSection, ...]:
    return _WORKSPACE_BEFORE + _pack_sidebar()


_FORM11_SECTIONS: tuple[WorkspaceSection, ...] = (
    WorkspaceSection("review", "Review dashboard", "overview", "Overview", 1),
    WorkspaceSection(
        "report-setup", "Report setup", "report-options", "Report options", 2
    ),
)

_FALLBACK_SECTIONS: tuple[WorkspaceSection, ...] = (
    WorkspaceSection("review", "Review dashboard", "overview", "Overview", 1),
    WorkspaceSection(
        "report-setup", "Report setup", "report-options", "Report options", 2
    ),
)

REPORTING_FRAMEWORKS: tuple[ReportingFramework, ...] = (
    ReportingFramework(
        id="frs102-1a-ie",
        version="2024.09",
        label="FRS 102 Section 1A (Ireland)",
        available=True,
        sections=_frs_sections(),
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
                        lock=section.lock,
                        default=section.default,
                        built=section.built,
                        children=section.children,
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
        shown = (amount / Decimal("1000")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    else:
        shown = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return format(shown, "f")


def default_report_setup(year_end: YearEnd, currency: str) -> ReportSetupWrite:
    """Year-and-symbol headings, matching an unsaved PDF, until a practice saves."""
    headings = column_headings(
        period_end=year_end.period_end,
        currency_code=currency or "GBP",
        comparative=True,
    )
    current = headings[0]
    prior = headings[1]
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
            as_at_current=current,
            as_at_prior=prior,
            ended_current=current,
            ended_prior=prior,
        ),
        sections=None,
    )


def _stored_sections(previous: object) -> dict[str, bool] | None:
    if not isinstance(previous, dict):
        return None
    raw = previous.get("sections")
    if not isinstance(raw, dict) or not raw:
        return None
    kept: dict[str, bool] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, bool):
            return None
        kept[key] = value
    return kept


def _stored_setup(year_end: YearEnd, currency: str) -> ReportSetupWrite:
    raw = year_end.report_setup
    if raw is None:
        return default_report_setup(year_end, currency)
    return ReportSetupWrite.model_validate(raw)


def report_setup_response(year_end: YearEnd, currency: str) -> ReportSetupResponse:
    cleaned = currency.strip().upper() or "GBP"
    setup = _stored_setup(year_end, cleaned)
    unit_label, thousands_label = rounding_labels(cleaned)
    return ReportSetupResponse(
        basis_id=year_end.pack_id,
        basis_version=year_end.pack_version,
        basis_label=framework_label(year_end.pack_id, year_end.pack_version),
        rounding=setup.rounding,
        statement_type=setup.statement_type,
        face_dates=setup.face_dates,
        column_headers=setup.column_headers,
        sections=setup.sections,
        trial_balance_period_start=year_end.period_start,
        trial_balance_period_end=year_end.period_end,
        currency=cleaned,
        rounding_unit_label=unit_label,
        rounding_thousands_label=thousands_label,
    )


async def save_report_setup(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    year_end: YearEnd,
    body: ReportSetupWrite,
    currency: str,
) -> ReportSetupResponse:
    """Replace display settings. Period columns and the pack pin stay put.

    Omitting ``sections`` keeps the map already stored. An empty map clears
    overrides, so it is not stored as every section off. A locked section
    set to false is rejected before this assignment.
    """
    previous = year_end.report_setup
    stored = body.model_dump(mode="json")
    if body.sections is None:
        kept = _stored_sections(previous)
        if kept is None:
            stored.pop("sections", None)
        else:
            stored["sections"] = kept
    elif not body.sections:
        stored.pop("sections", None)
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
    return report_setup_response(year_end, currency)


def _display_defaults(
    year_end: YearEnd, currency: str, sections: dict[str, bool] | None
) -> dict[str, object]:
    stored: dict[str, object] = default_report_setup(year_end, currency).model_dump(
        mode="json"
    )
    stored.pop("sections", None)
    if sections:
        stored["sections"] = sections
    return stored


async def reset_report_setup(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    year_end: YearEnd,
    currency: str,
    scope: Literal["sections", "display"],
) -> ReportSetupResponse:
    """Clear one saved override. Sections return to the pack. Display returns to defaults."""
    previous = year_end.report_setup
    if scope == "sections":
        if isinstance(previous, dict) and any(key != "sections" for key in previous):
            kept = dict(previous)
            kept.pop("sections", None)
            year_end.report_setup = kept
        else:
            year_end.report_setup = None
    else:
        year_end.report_setup = _display_defaults(
            year_end, currency, _stored_sections(previous)
        )
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="report_setup_reset",
        entity_type="year_end",
        entity_id=year_end.id,
        old_value=previous if isinstance(previous, dict) else None,
        new_value=(
            year_end.report_setup if isinstance(year_end.report_setup, dict) else None
        ),
    )
    return report_setup_response(year_end, currency)
