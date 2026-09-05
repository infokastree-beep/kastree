"""Materiality auto-suggestion — ISA 320-style mid-range SaaS defaults.

Tracked-gaps design: trading → 5–10% of |PBT| (mid 7.5%); holding → 3–10% of
|total equity| (mid 6.5%). Suggestion only — never auto-applied. Accountant
retains professional judgment.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol, Sequence

CompanyType = Literal["trading", "holding"]
BenchmarkBasis = Literal["profit_before_tax", "total_equity"]

# Mid-range of the documented ISA 320-derived bands.
TRADING_RANGE = (Decimal("5.00"), Decimal("10.00"))
HOLDING_RANGE = (Decimal("3.00"), Decimal("10.00"))
TRADING_MID_PCT = Decimal("7.50")
HOLDING_MID_PCT = Decimal("6.50")

MONEY = Decimal("0.01")
PCT = Decimal("0.01")
# "Meaningfully differs" — ≥ 0.5pp on the % threshold, or ≥ 1.00 on abs.
PCT_MEANINGFUL_DELTA = Decimal("0.50")
ABS_MEANINGFUL_DELTA = Decimal("1.00")
ZERO_BASE_TOLERANCE = Decimal("0.005")

DISCLAIMER = (
    "Indicative SaaS default from ISA 320-style benchmarks — "
    "not an audit determination."
)


class StatementLineLike(Protocol):
    line_item_code: str
    amount: Decimal


class MaterialitySuggestion:
    """Plain result object for the router / schema layer."""

    __slots__ = (
        "available",
        "message",
        "company_type",
        "benchmark_basis",
        "benchmark_amount",
        "range_pct_low",
        "range_pct_high",
        "suggested_pct",
        "suggested_abs",
        "current_pct",
        "current_abs",
        "dismissed",
        "disclaimer",
    )

    def __init__(
        self,
        *,
        available: bool,
        message: str | None,
        company_type: CompanyType,
        benchmark_basis: BenchmarkBasis | None,
        benchmark_amount: Decimal | None,
        range_pct_low: Decimal | None,
        range_pct_high: Decimal | None,
        suggested_pct: Decimal | None,
        suggested_abs: Decimal | None,
        current_pct: Decimal,
        current_abs: Decimal,
        dismissed: bool,
    ) -> None:
        self.available = available
        self.message = message
        self.company_type = company_type
        self.benchmark_basis = benchmark_basis
        self.benchmark_amount = benchmark_amount
        self.range_pct_low = range_pct_low
        self.range_pct_high = range_pct_high
        self.suggested_pct = suggested_pct
        self.suggested_abs = suggested_abs
        self.current_pct = current_pct
        self.current_abs = current_abs
        self.dismissed = dismissed
        self.disclaimer = DISCLAIMER


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _pct(value: Decimal) -> Decimal:
    return value.quantize(PCT, rounding=ROUND_HALF_UP)


def _line_amount(lines: Sequence[StatementLineLike], code: str) -> Decimal | None:
    for line in lines:
        if line.line_item_code == code:
            return Decimal(line.amount)
    return None


def _meaningfully_differs(
    *,
    suggested_pct: Decimal,
    suggested_abs: Decimal,
    current_pct: Decimal,
    current_abs: Decimal,
) -> bool:
    pct_delta = abs(suggested_pct - current_pct)
    abs_delta = abs(suggested_abs - current_abs)
    return pct_delta >= PCT_MEANINGFUL_DELTA or abs_delta >= ABS_MEANINGFUL_DELTA


def suggest_materiality(
    *,
    company_type: CompanyType,
    current_pct: Decimal,
    current_abs: Decimal,
    sopl_lines: Sequence[StatementLineLike],
    sofp_lines: Sequence[StatementLineLike],
    dismissed: bool,
) -> MaterialitySuggestion:
    """Compute a soft materiality suggestion from statement figures.

    Returns ``available=False`` when the base is nil, the suggestion matches
    current settings, or the user has dismissed the banner for this company.
    """
    current_pct_q = _pct(Decimal(current_pct))
    current_abs_q = _money(Decimal(current_abs))

    if company_type == "holding":
        basis: BenchmarkBasis = "total_equity"
        base = _line_amount(sofp_lines, "total_equity")
        mid = HOLDING_MID_PCT
        low, high = HOLDING_RANGE
        basis_label = "total equity"
    else:
        basis = "profit_before_tax"
        base = _line_amount(sopl_lines, "profit_before_tax")
        mid = TRADING_MID_PCT
        low, high = TRADING_RANGE
        basis_label = "profit before tax"

    if base is None:
        return MaterialitySuggestion(
            available=False,
            message=(
                f"Cannot suggest materiality — {basis_label} is missing from "
                "generated statements."
            ),
            company_type=company_type,
            benchmark_basis=basis,
            benchmark_amount=None,
            range_pct_low=low,
            range_pct_high=high,
            suggested_pct=None,
            suggested_abs=None,
            current_pct=current_pct_q,
            current_abs=current_abs_q,
            dismissed=dismissed,
        )

    if abs(base) <= ZERO_BASE_TOLERANCE:
        return MaterialitySuggestion(
            available=False,
            message=(
                f"Cannot suggest materiality — {basis_label} is nil. "
                "Set thresholds manually."
            ),
            company_type=company_type,
            benchmark_basis=basis,
            benchmark_amount=_money(base),
            range_pct_low=low,
            range_pct_high=high,
            suggested_pct=None,
            suggested_abs=None,
            current_pct=current_pct_q,
            current_abs=current_abs_q,
            dismissed=dismissed,
        )

    suggested_pct = _pct(mid)
    suggested_abs = _money(abs(base) * mid / Decimal("100"))
    message = (
        f"We suggest {suggested_pct}% ({suggested_abs} absolute) based on "
        f"{suggested_pct}% of {basis_label} — apply it?"
    )

    if dismissed:
        return MaterialitySuggestion(
            available=False,
            message=message,
            company_type=company_type,
            benchmark_basis=basis,
            benchmark_amount=_money(base),
            range_pct_low=low,
            range_pct_high=high,
            suggested_pct=suggested_pct,
            suggested_abs=suggested_abs,
            current_pct=current_pct_q,
            current_abs=current_abs_q,
            dismissed=True,
        )

    if not _meaningfully_differs(
        suggested_pct=suggested_pct,
        suggested_abs=suggested_abs,
        current_pct=current_pct_q,
        current_abs=current_abs_q,
    ):
        return MaterialitySuggestion(
            available=False,
            message=(
                "Current materiality already matches the suggested "
                f"{suggested_pct}% / {suggested_abs} thresholds."
            ),
            company_type=company_type,
            benchmark_basis=basis,
            benchmark_amount=_money(base),
            range_pct_low=low,
            range_pct_high=high,
            suggested_pct=suggested_pct,
            suggested_abs=suggested_abs,
            current_pct=current_pct_q,
            current_abs=current_abs_q,
            dismissed=False,
        )

    return MaterialitySuggestion(
        available=True,
        message=message,
        company_type=company_type,
        benchmark_basis=basis,
        benchmark_amount=_money(base),
        range_pct_low=low,
        range_pct_high=high,
        suggested_pct=suggested_pct,
        suggested_abs=suggested_abs,
        current_pct=current_pct_q,
        current_abs=current_abs_q,
        dismissed=False,
    )
