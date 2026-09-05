"""Multi-period statement metrics for the statements performance overview.

Pulls already-generated SOPL/SOFP line amounts across every historical trial
balance for a company — no new financial calculations, only selection and
serialisation of existing statement figures.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence
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

# Soft cap so a company with decades of history stays responsive.
MAX_PERIODS = 36


@dataclass(frozen=True, slots=True)
class PeriodMetrics:
    tb_id: UUID
    period_end: date
    metrics: dict[str, Decimal | None]


def _quantize(amount: Decimal | None) -> Decimal | None:
    if amount is None:
        return None
    return Decimal(amount).quantize(Decimal("0.01"))


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
        shares[code] = magnitude.quantize(Decimal("0.01"))
    return shares
