"""Review-dashboard groups, Fix targets, and the finalise count."""

from __future__ import annotations

import uuid

from app.services.dashboard_groups import (
    blocking_failure_count,
    present_check,
)
from app.services.draft_workflow import Dashboard, _dashboard_dict
from app.services.reconciliation import ReconciliationCheck


def _check(code: str, severity: str, passed: bool = False) -> ReconciliationCheck:
    return ReconciliationCheck(
        code=code, severity=severity, passed=passed, message=f"{code} message"
    )


def test_fix_targets_match_the_review_pages() -> None:
    assert present_check("V-CO-008").area == "Company details"
    assert present_check("V-CO-008").fix.section == "company-details"
    assert present_check("V-CO-010").fix.section == "company-details"
    assert present_check("V-CO-011").fix.section == "company-details"
    assert present_check("V-CO-018").area == "Figures"
    assert present_check("V-CO-018").fix.section == "income"
    assert present_check("V-CO-019").area == "Disclosures"
    assert present_check("V-CO-019").fix.section == "disclosures"
    assert present_check("V-CO-020").area == "Review"
    assert present_check("V-CO-020").fix.section == "review"
    assert present_check("V-CO-020").fix.anchor == "audit-exemption-claim"
    assert present_check("V-CO-021").fix.section == "review"
    for code in ("V-CO-022", "V-CO-023", "V-CO-024"):
        shown = present_check(code)
        assert shown.area == "Review"
        assert shown.fix.section == "review"
        assert shown.fix.anchor == "audit-exemption-conditions"
    assert present_check("V-DISC-001").fix.section == "disclosures"
    assert present_check("V-GATE-001").fix.anchor == "statutory-first-period-gate"
    assert present_check("V-CMP-001").fix.section == "sofp"
    assert present_check("V-SEC-006").fix.section == "sections-setup"
    assert present_check("V-SEC-007").fix.section == "report-setup"
    assert present_check("V-MAP-001").fix.section == "sub-lines"
    assert present_check("V-RE-001").fix.section == "income"
    assert present_check("V-FA-001").fix.note == "N2_FA"
    assert present_check("V-TB-001").area == "Figures"


def test_blocking_count_skips_notices_that_do_not_stop_finalise() -> None:
    checks = (
        _check("V-DISC-001", "CRITICAL"),
        _check("V-CO-008", "NOTICE"),
        _check("V-CO-010", "WARNING"),
        _check("V-CO-012", "NOTICE"),
        _check("V-CO-007", "NOTICE"),
        _check("V-SEC-007", "NOTICE"),
        _check("V-FA-001", "WARNING"),
        _check("V-CO-001", "WARNING", passed=True),
    )
    assert blocking_failure_count(checks) == 3


def test_dashboard_payload_keeps_the_engine_disclosure_message() -> None:
    message = "Unanswered disclosure questions: ['PENSION_COMMITMENT']"
    board = Dashboard(
        draft_id=uuid.uuid4(),
        status="draft",
        row_version=1,
        traffic="red",
        can_finalise=False,
        checks=(
            ReconciliationCheck(
                code="V-DISC-001",
                severity="CRITICAL",
                passed=False,
                message=message,
            ),
        ),
        unanswered_disclosures=("PENSION_COMMITMENT",),
        carried_disclosures=(),
    )
    payload = _dashboard_dict(board)
    assert payload["unanswered_count"] == 1
    assert payload["blocking_count"] == 1
    checks = payload["checks"]
    assert isinstance(checks, list)
    row = checks[0]
    assert isinstance(row, dict)
    assert row["message"] == message
    assert row["area"] == "Disclosures"
    fix = row["fix"]
    assert isinstance(fix, dict)
    assert fix["section"] == "disclosures"
