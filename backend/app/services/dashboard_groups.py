"""Plain-English groups and Fix targets for the review dashboard.

The engine message for V-DISC-001 stays in place so the unanswered parser
can keep reading it. The screen uses unanswered_count instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.company_details import blocks_final
from app.services.reconciliation import ReconciliationCheck


@dataclass(frozen=True)
class CheckFix:
    section: str
    note: str | None = None
    anchor: str | None = None


@dataclass(frozen=True)
class CheckPresentation:
    area: str
    fix: CheckFix


_FIXES: dict[str, CheckPresentation] = {
    "V-CO-001": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-002": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-003": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-004": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-005": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-006": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-007": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-008": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-009": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-010": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-025": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-026": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-011": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-037": CheckPresentation(
        "Comparatives",
        CheckFix("review", anchor="statutory-first-period-gate"),
    ),
    "V-CO-038": CheckPresentation(
        "Practice letterhead",
        CheckFix("settings", anchor="practice-letterhead"),
    ),
    "V-CO-027": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-029": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-030": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-031": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-032": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-033": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-034": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-035": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-036": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-012": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-013": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-014": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-015": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-016": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-017": CheckPresentation("Company details", CheckFix("company-details")),
    "V-CO-018": CheckPresentation("Figures", CheckFix("income")),
    "V-CO-019": CheckPresentation("Disclosures", CheckFix("disclosures")),
    "V-CO-020": CheckPresentation(
        "Review",
        CheckFix("review", anchor="audit-exemption-claim"),
    ),
    "V-CO-021": CheckPresentation(
        "Review",
        CheckFix("review", anchor="audit-exemption-claim"),
    ),
    "V-CO-022": CheckPresentation(
        "Review",
        CheckFix("review", anchor="audit-exemption-conditions"),
    ),
    "V-CO-023": CheckPresentation(
        "Review",
        CheckFix("review", anchor="audit-exemption-conditions"),
    ),
    "V-CO-024": CheckPresentation(
        "Review",
        CheckFix("review", anchor="audit-exemption-conditions"),
    ),
    "V-DISC-001": CheckPresentation("Disclosures", CheckFix("disclosures")),
    "V-NOTE-001": CheckPresentation("Disclosures", CheckFix("notes")),
    "V-NOTE-002": CheckPresentation("Disclosures", CheckFix("notes")),
    "V-NOTE-003": CheckPresentation("Disclosures", CheckFix("notes")),
    "V-GATE-001": CheckPresentation(
        "Comparatives",
        CheckFix("review", anchor="statutory-first-period-gate"),
    ),
    "V-CMP-001": CheckPresentation("Comparatives", CheckFix("sofp")),
    "V-CMP-002": CheckPresentation("Comparatives", CheckFix("sofp")),
    "V-SEC-005": CheckPresentation("Sections", CheckFix("sections-setup")),
    "V-SEC-006": CheckPresentation("Sections", CheckFix("sections-setup")),
    "V-SEC-007": CheckPresentation("Setup", CheckFix("report-setup")),
    "V-MAP-001": CheckPresentation("Figures", CheckFix("sub-lines")),
    "V-TB-001": CheckPresentation("Figures", CheckFix("sofp")),
    "V-BS-001": CheckPresentation("Figures", CheckFix("sofp")),
    "V-BANK-001": CheckPresentation("Figures", CheckFix("sofp")),
    "V-RE-001": CheckPresentation("Figures", CheckFix("income")),
    "V-FA-001": CheckPresentation("Figures", CheckFix("notes", note="N2_FA")),
}

_OTHER = CheckPresentation("Other", CheckFix("review"))

GROUP_ORDER = (
    "Company details",
    "Practice letterhead",
    "Disclosures",
    "Comparatives",
    "Sections",
    "Setup",
    "Figures",
    "Review",
    "Other",
)


def present_check(code: str) -> CheckPresentation:
    return _FIXES.get(code, _OTHER)


def stops_finalise(check: ReconciliationCheck) -> bool:
    """True when this failed check is one of the reasons Finalise stays off."""
    if check.passed:
        return False
    if check.severity in {"CRITICAL", "BLOCKED"}:
        return True
    return blocks_final((check,))


def blocking_failure_count(checks: tuple[ReconciliationCheck, ...]) -> int:
    return sum(1 for item in checks if stops_finalise(item))
