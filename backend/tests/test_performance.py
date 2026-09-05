"""Unit tests for multi-period performance overview helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.services.performance import (
    build_period_metrics,
    expense_share_amounts,
    select_history_periods,
)


def test_build_period_metrics_quantizes_and_fills_missing() -> None:
    tb_id = uuid4()
    period = build_period_metrics(
        tb_id=tb_id,
        period_end=date(2026, 9, 20),
        line_amounts={
            "revenue": Decimal("816600.1"),
            "gross_profit": Decimal("337800"),
            "depreciation": Decimal("-54400"),
        },
    )
    assert period.tb_id == tb_id
    assert period.metrics["revenue"] == Decimal("816600.10")
    assert period.metrics["gross_profit"] == Decimal("337800.00")
    assert period.metrics["depreciation"] == Decimal("-54400.00")
    assert period.metrics["cash"] is None
    assert period.metrics["net_profit"] is None


def test_select_history_periods_caps_and_filters_future() -> None:
    early = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 7, 8),
        line_amounts={"revenue": Decimal("1")},
    )
    mid = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 8, 15),
        line_amounts={"revenue": Decimal("2")},
    )
    current = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 9, 20),
        line_amounts={"revenue": Decimal("3")},
    )
    future = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 10, 1),
        line_amounts={"revenue": Decimal("4")},
    )
    selected = select_history_periods(
        [future, current, early, mid],
        as_of=date(2026, 9, 20),
        limit=2,
    )
    assert [p.period_end for p in selected] == [
        date(2026, 8, 15),
        date(2026, 9, 20),
    ]


def test_select_history_allows_single_period() -> None:
    only = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 9, 20),
        line_amounts={"revenue": Decimal("100")},
    )
    selected = select_history_periods([only], as_of=date(2026, 9, 20))
    assert len(selected) == 1


def test_expense_share_uses_absolute_values() -> None:
    shares = expense_share_amounts(
        {
            "cost_of_sales": Decimal("478800"),
            "operating_expenses": Decimal("469200"),
            "depreciation": Decimal("-54400"),
            "revenue": Decimal("816600"),
        }
    )
    assert shares == {
        "cost_of_sales": Decimal("478800.00"),
        "operating_expenses": Decimal("469200.00"),
        "depreciation": Decimal("54400.00"),
    }
