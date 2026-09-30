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


def _met(year: YearSize, limits: _Limits) -> int:
    return sum(
        (
            year.turnover <= limits.turnover,
            year.balance_sheet_total <= limits.balance_sheet,
            year.employees <= limits.employees,
        )
    )


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
    if first_financial_period:
        message = (
            f"Current year meets {current_met} of 3 small-company conditions. "
            "This year end is a first financial period, so there is no preceding year."
        )
    else:
        message = (
            f"Current year meets {current_met} of 3 small-company conditions. "
            f"Preceding year meets {preceding_met} of 3. "
            "The pack requires 2 of 3 in both years."
        )
    return SizeAssessment(
        eligible=eligible,
        current_conditions_met=current_met,
        preceding_conditions_met=preceding_met,
        message=message,
    )


async def record_size_assessment(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    assessment: SizeAssessment,
) -> YearEnd:
    await aset_rls_org_id(session, org_id)
    year_end.size_eligible = assessment.eligible
    year_end.size_message = assessment.message
    year_end.size_current_met = assessment.current_conditions_met
    year_end.size_preceding_met = assessment.preceding_conditions_met
    year_end.size_checked_at = datetime.now(timezone.utc)
    await session.flush()
    return year_end
