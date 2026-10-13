"""Small-company size test for the pinned pack.

The pack carries the thresholds. This module does not hard-code the euro
amounts. It implements only the rule the specification states: 2 of 3,
current year and preceding year. A first financial period has no preceding
year, so only the current year is tested.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.services.audit import append_audit_log
from findraft.engine.money import D, money
from findraft.models.year_end import YearEnd

_THRESHOLD_KEYS = frozenset(
    {"regime", "currency", "rule", "years", "turnover", "balance_sheet", "employees"}
)


class SizeEligibilityRejected(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class YearSize:
    turnover: Decimal
    balance_sheet_total: Decimal
    employees: int


@dataclass(frozen=True)
class SizeAssessment:
    eligible: bool
    current_conditions_met: int
    preceding_conditions_met: int | None
    message: str


@dataclass(frozen=True)
class _Limits:
    currency: str
    turnover: Decimal
    balance_sheet: Decimal
    employees: int


def exact_amount(raw: str) -> Decimal:
    """Accept a non-negative amount that is already exact to the cent."""
    try:
        parsed = D(raw.strip())
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise SizeEligibilityRejected("Amount must be a decimal string") from exc
    cents = money(parsed)
    if cents != parsed or cents < 0:
        raise SizeEligibilityRejected("Amount must be a non-negative exact cent amount")
    return cents


def _limits(manifest: dict[str, object]) -> _Limits:
    block = manifest.get("thresholds")
    if not isinstance(block, dict) or set(block) != _THRESHOLD_KEYS:
        raise SizeEligibilityRejected("Pinned pack has no usable thresholds")
    if (
        block.get("regime") != "small"
        or block.get("rule") != "2-of-3"
        or block.get("years") != "current-and-preceding"
    ):
        raise SizeEligibilityRejected(
            "Pinned pack size rule is not the small-company test"
        )
    currency = block.get("currency")
    employees = block.get("employees")
    turnover = block.get("turnover")
    balance_sheet = block.get("balance_sheet")
    if not isinstance(currency, str) or len(currency) != 3:
        raise SizeEligibilityRejected("Pinned pack threshold currency is unusable")
    if isinstance(employees, bool) or not isinstance(employees, int) or employees < 0:
        raise SizeEligibilityRejected("Pinned pack employee threshold is unusable")
    if not isinstance(turnover, str) or not isinstance(balance_sheet, str):
        raise SizeEligibilityRejected(
            "Pinned pack money thresholds must be decimal strings"
        )
    return _Limits(
        currency=currency,
        turnover=exact_amount(turnover),
        balance_sheet=exact_amount(balance_sheet),
        employees=employees,
    )


def _outcomes(year: YearSize, limits: _Limits) -> tuple[tuple[str, bool], ...]:
    return (
        ("turnover", year.turnover <= limits.turnover),
        ("balance sheet total", year.balance_sheet_total <= limits.balance_sheet),
        ("employees", year.employees <= limits.employees),
    )


def _met(year: YearSize, limits: _Limits) -> int:
    return sum(int(met) for _name, met in _outcomes(year, limits))


def _year_clause(label: str, year: YearSize, limits: _Limits) -> str:
    parts = [
        f"{name} {'met' if met else 'not met'}" for name, met in _outcomes(year, limits)
    ]
    return f"{label}: {'; '.join(parts)}."


def _size_rule_note(manifest: dict[str, object]) -> str:
    """Reviewer-to-confirm pack sentence. It is not invented here."""
    note = manifest.get("size_rule_note")
    if not isinstance(note, dict) or set(note) != {"source_status", "text"}:
        raise SizeEligibilityRejected("Pinned pack has no size-rule note")
    text = note.get("text")
    if note.get("source_status") != "reviewer-to-confirm" or not isinstance(text, str):
        raise SizeEligibilityRejected(
            "Pinned pack size-rule note is not marked reviewer-to-confirm"
        )
    cleaned = text.strip()
    if not cleaned or "eligible" in cleaned.casefold():
        raise SizeEligibilityRejected("Pinned pack size-rule note is unusable")
    return cleaned


def assess_size(
    manifest: dict[str, object],
    *,
    company_currency: str,
    current: YearSize,
    preceding: YearSize | None,
    first_financial_period: bool,
) -> SizeAssessment:
    """Return whether the company meets the pinned pack's small-company test."""
    limits = _limits(manifest)
    if company_currency != limits.currency:
        raise SizeEligibilityRejected(
            f"Company currency is {company_currency}; this pack's thresholds are {limits.currency}"
        )
    if first_financial_period and preceding is not None:
        raise SizeEligibilityRejected(
            "A first financial period has no preceding-year size figures"
        )
    if not first_financial_period and preceding is None:
        raise SizeEligibilityRejected("Preceding-year size figures are required")
    current_met = _met(current, limits)
    preceding_met = None if preceding is None else _met(preceding, limits)
    eligible = current_met >= 2 and (preceding_met is None or preceding_met >= 2)
    parts = [_year_clause("Current year", current, limits)]
    if first_financial_period:
        parts.append(
            "This year end is a first financial period, so there is no preceding year."
        )
    elif preceding is not None:
        parts.append(_year_clause("Preceding year", preceding, limits))
    failed_a_condition = current_met < 3 or (
        preceding_met is not None and preceding_met < 3
    )
    if eligible and failed_a_condition:
        parts.append(_size_rule_note(manifest))
    message = " ".join(parts)
    return SizeAssessment(
        eligible=eligible,
        current_conditions_met=current_met,
        preceding_conditions_met=preceding_met,
        message=message,
    )


def size_audit_value(year_end: YearEnd) -> dict[str, object]:
    """Decision and headcount only. Turnover and balance-sheet amounts stay off the log."""
    return {
        "eligible": year_end.size_eligible,
        "current_conditions_met": year_end.size_current_met,
        "preceding_conditions_met": year_end.size_preceding_met,
        "current_employees": year_end.size_current_employees,
        "preceding_employees": year_end.size_preceding_employees,
        "confirmed": True,
    }


async def record_size_assessment(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    year_end: YearEnd,
    assessment: SizeAssessment,
    current: YearSize,
    preceding: YearSize | None,
) -> YearEnd:
    await aset_rls_org_id(session, org_id)
    previous = None if year_end.size_checked_at is None else size_audit_value(year_end)
    year_end.size_current_turnover = current.turnover
    year_end.size_current_balance_sheet = current.balance_sheet_total
    year_end.size_current_employees = current.employees
    if preceding is None:
        year_end.size_preceding_turnover = None
        year_end.size_preceding_balance_sheet = None
        year_end.size_preceding_employees = None
    else:
        year_end.size_preceding_turnover = preceding.turnover
        year_end.size_preceding_balance_sheet = preceding.balance_sheet_total
        year_end.size_preceding_employees = preceding.employees
    year_end.size_eligible = assessment.eligible
    year_end.size_message = assessment.message
    year_end.size_current_met = assessment.current_conditions_met
    year_end.size_preceding_met = assessment.preceding_conditions_met
    year_end.size_checked_at = datetime.now(timezone.utc)
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="size_eligibility_recorded",
        entity_type="year_end",
        entity_id=year_end.id,
        old_value=previous,
        new_value=size_audit_value(year_end),
    )
    await session.flush()
    return year_end
