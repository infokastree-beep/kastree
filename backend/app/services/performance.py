"""Multi-period statement metrics for the statements performance overview.

Pulls already-generated SOPL/SOFP line amounts across every historical trial
balance for a company — no new financial calculations beyond selection,
serialisation, and optional calendar aggregation of existing statement figures.

Aggregation rules (Monthly / Quarterly / Yearly):
- Flow metrics are summed across TBs in the bucket.
- Stock (balance-sheet) metrics take the last TB in the bucket by period_end.
- Incomplete calendar buckets are included and flagged ``is_partial`` — never
  omitted while waiting for the quarter/year to finish.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Sequence
from uuid import UUID

# Face-line codes we surface on the performance overview.
KPI_CODES: tuple[str, ...] = (
    "revenue",
    "gross_profit",
    "net_profit",
    "cash",
)
EXPENSE_CODES: tuple[str, ...] = (
    "cost_of_sales",
    "operating_expenses",
    "depreciation",
)
METRIC_CODES: tuple[str, ...] = tuple(dict.fromkeys((*KPI_CODES, *EXPENSE_CODES)))

# P&L / activity lines — sum within a quarter or year.
FLOW_METRIC_CODES: frozenset[str] = frozenset(
    {
        "revenue",
        "gross_profit",
        "net_profit",
        "cost_of_sales",
        "operating_expenses",
        "depreciation",
    }
)
# Point-in-time SOFP lines — last period in the bucket only (never summed).
STOCK_METRIC_CODES: frozenset[str] = frozenset({"cash"})

Granularity = Literal["monthly", "quarterly", "yearly"]

# Soft cap so a company with decades of history stays responsive.
MAX_PERIODS = 36

_MONEY = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class PeriodMetrics:
    tb_id: UUID
    period_end: date
    metrics: dict[str, Decimal | None]


@dataclass(frozen=True, slots=True)
class AggregatedPeriodMetrics:
    """One chart/KPI point after optional calendar aggregation."""

    tb_id: UUID
    period_end: date
    metrics: dict[str, Decimal | None]
    bucket_key: str
    is_partial: bool
    source_period_count: int


def _quantize(amount: Decimal | None) -> Decimal | None:
    if amount is None:
        return None
    return Decimal(amount).quantize(_MONEY, rounding=ROUND_HALF_UP)


def build_period_metrics(
    *,
    tb_id: UUID,
    period_end: date,
    line_amounts: dict[str, Decimal],
) -> PeriodMetrics:
    """Map raw line amounts onto the overview metric set."""
    metrics: dict[str, Decimal | None] = {
        code: _quantize(line_amounts.get(code)) for code in METRIC_CODES
    }
    return PeriodMetrics(tb_id=tb_id, period_end=period_end, metrics=metrics)


def select_history_periods(
    periods: Sequence[PeriodMetrics],
    *,
    as_of: date,
    limit: int = MAX_PERIODS,
) -> list[PeriodMetrics]:
    """Keep periods at or before ``as_of``, oldest→newest, capped at ``limit``."""
    filtered = [p for p in periods if p.period_end <= as_of]
    filtered.sort(key=lambda p: (p.period_end, str(p.tb_id)))
    if len(filtered) > limit:
        filtered = filtered[-limit:]
    return filtered


def expense_share_amounts(
    metrics: dict[str, Decimal | None],
) -> dict[str, Decimal]:
    """Absolute amounts for the expense breakdown (nil/zero codes omitted)."""
    shares: dict[str, Decimal] = {}
    for code in EXPENSE_CODES:
        raw = metrics.get(code)
        if raw is None:
            continue
        magnitude = abs(Decimal(raw))
        if magnitude == 0:
            continue
        shares[code] = magnitude.quantize(_MONEY, rounding=ROUND_HALF_UP)
    return shares


def bucket_key(period_end: date, granularity: Granularity) -> str:
    """Stable group id: ISO date, ``YYYY-Qn``, or ``YYYY``."""
    if granularity == "monthly":
        return period_end.isoformat()
    if granularity == "quarterly":
        quarter = (period_end.month - 1) // 3 + 1
        return f"{period_end.year}-Q{quarter}"
    return str(period_end.year)


def calendar_bucket_end(key: str, granularity: Granularity) -> date | None:
    """Last calendar day of a quarterly/yearly bucket; ``None`` for monthly."""
    if granularity == "monthly":
        return None
    if granularity == "quarterly":
        year_str, quarter_str = key.split("-Q", 1)
        year = int(year_str)
        quarter = int(quarter_str)
        last_month = quarter * 3
        last_day = calendar.monthrange(year, last_month)[1]
        return date(year, last_month, last_day)
    if granularity == "yearly":
        return date(int(key), 12, 31)
    return None


def growth_pct(
    current: Decimal | None,
    prior: Decimal | None,
) -> Decimal | None:
    """Period-over-period % using the same formula as the Performance UI.

    On Quarterly/Yearly views, ``prior`` must be the prior *aggregated bucket*,
    never a raw prior month.
    """
    if current is None or prior is None or prior == 0:
        return None
    return ((current - prior) / abs(prior) * Decimal("100")).quantize(
        Decimal("0.1"),
        rounding=ROUND_HALF_UP,
    )


def aggregate_performance_periods(
    periods: Sequence[PeriodMetrics],
    *,
    granularity: Granularity,
    as_of: date,
) -> list[AggregatedPeriodMetrics]:
    """Aggregate monthly statement metrics into calendar quarters or years.

    Assumptions
    -----------
    Each TB's flow metrics represent that period's activity (non-overlapping),
    matching MoM variance. YTD-overlapping uploads are out of scope.

    Partial buckets
    ---------------
    If the bucket's calendar end is after ``as_of``, the bucket is still
    returned with ``is_partial=True`` (show what's available; do not wait).
    """
    ordered = sorted(periods, key=lambda p: (p.period_end, str(p.tb_id)))
    if not ordered:
        return []

    if granularity == "monthly":
        return [
            AggregatedPeriodMetrics(
                tb_id=p.tb_id,
                period_end=p.period_end,
                metrics=dict(p.metrics),
                bucket_key=bucket_key(p.period_end, "monthly"),
                is_partial=False,
                source_period_count=1,
            )
            for p in ordered
        ]

    groups: dict[str, list[PeriodMetrics]] = {}
    order: list[str] = []
    for period in ordered:
        key = bucket_key(period.period_end, granularity)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(period)

    aggregated: list[AggregatedPeriodMetrics] = []
    for key in order:
        members = groups[key]
        last = members[-1]
        metrics: dict[str, Decimal | None] = {}
        for code in METRIC_CODES:
            if code in STOCK_METRIC_CODES:
                metrics[code] = last.metrics.get(code)
                continue
            total = Decimal("0")
            any_value = False
            for member in members:
                raw = member.metrics.get(code)
                if raw is None:
                    continue
                any_value = True
                total += Decimal(raw)
            metrics[code] = (
                total.quantize(_MONEY, rounding=ROUND_HALF_UP) if any_value else None
            )

        cal_end = calendar_bucket_end(key, granularity)
        is_partial = cal_end is not None and as_of < cal_end
        aggregated.append(
            AggregatedPeriodMetrics(
                tb_id=last.tb_id,
                period_end=last.period_end,
                metrics=metrics,
                bucket_key=key,
                is_partial=is_partial,
                source_period_count=len(members),
            )
        )
    return aggregated
