"""Unit tests for multi-period performance overview helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.services.performance import (
    aggregate_performance_periods,
    build_period_metrics,
    expense_share_amounts,
    growth_pct,
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


def test_monthly_aggregation_is_identity() -> None:
    a = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 8, 31),
        line_amounts={"revenue": Decimal("100"), "cash": Decimal("10")},
    )
    b = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 9, 30),
        line_amounts={"revenue": Decimal("200"), "cash": Decimal("20")},
    )
    out = aggregate_performance_periods(
        [a, b], granularity="monthly", as_of=date(2026, 9, 30)
    )
    assert len(out) == 2
    assert out[0].bucket_key == "2026-08-31"
    assert out[0].is_partial is False
    assert out[0].source_period_count == 1
    assert out[0].metrics["revenue"] == Decimal("100.00")
    assert out[1].metrics["cash"] == Decimal("20.00")


def test_quarterly_sums_flows_and_takes_last_stock() -> None:
    """Q3: Jul+Aug+Sep — revenue/net_profit sum; cash = Sep only."""
    jul = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 7, 31),
        line_amounts={
            "revenue": Decimal("100"),
            "net_profit": Decimal("10"),
            "cash": Decimal("1000"),
            "cost_of_sales": Decimal("40"),
        },
    )
    aug = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 8, 31),
        line_amounts={
            "revenue": Decimal("200"),
            "net_profit": Decimal("20"),
            "cash": Decimal("2000"),
            "cost_of_sales": Decimal("50"),
        },
    )
    sep = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 9, 20),
        line_amounts={
            "revenue": Decimal("50"),
            "net_profit": Decimal("5"),
            "cash": Decimal("3500"),
            "cost_of_sales": Decimal("10"),
        },
    )
    out = aggregate_performance_periods(
        [jul, aug, sep],
        granularity="quarterly",
        as_of=date(2026, 9, 20),
    )
    assert len(out) == 1
    q3 = out[0]
    assert q3.bucket_key == "2026-Q3"
    assert q3.is_partial is True  # as_of before 30 Sep
    assert q3.source_period_count == 3
    assert q3.period_end == date(2026, 9, 20)
    assert q3.tb_id == sep.tb_id
    assert q3.metrics["revenue"] == Decimal("350.00")
    assert q3.metrics["net_profit"] == Decimal("35.00")
    assert q3.metrics["cost_of_sales"] == Decimal("100.00")
    assert q3.metrics["cash"] == Decimal("3500.00")
    # Prove cash was NOT summed (1000+2000+3500 = 6500).
    assert q3.metrics["cash"] != Decimal("6500.00")


def test_yearly_partial_and_skips_null_flows() -> None:
    a = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2025, 12, 31),
        line_amounts={"revenue": Decimal("1000"), "cash": Decimal("100")},
    )
    b = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 3, 31),
        line_amounts={"cash": Decimal("200")},  # revenue missing → skip, not 0
    )
    c = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 6, 30),
        line_amounts={"revenue": Decimal("400"), "cash": Decimal("300")},
    )
    out = aggregate_performance_periods(
        [a, b, c], granularity="yearly", as_of=date(2026, 6, 30)
    )
    assert [p.bucket_key for p in out] == ["2025", "2026"]
    assert out[0].is_partial is False
    assert out[1].is_partial is True
    assert out[0].metrics["revenue"] == Decimal("1000.00")
    assert out[1].metrics["revenue"] == Decimal("400.00")  # null month skipped
    assert out[1].metrics["cash"] == Decimal("300.00")


def test_quarterly_growth_uses_prior_aggregated_bucket_not_prior_month() -> None:
    """Growth on Quarterly view must be Q3-vs-Q2, never vs the last month of Q2.

    Setup:
      Q2: Apr revenue 100, May revenue 200  → aggregated 300; last month = 200
      Q3: Jul revenue 50,  Aug revenue 50   → aggregated 100

    Correct growth (vs prior bucket): (100 - 300) / 300 = -66.7%
    Wrong growth (vs prior month May): (100 - 200) / 200 = -50.0%
    """
    apr = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 4, 30),
        line_amounts={"revenue": Decimal("100"), "cash": Decimal("10")},
    )
    may = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 5, 31),
        line_amounts={"revenue": Decimal("200"), "cash": Decimal("20")},
    )
    jul = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 7, 31),
        line_amounts={"revenue": Decimal("50"), "cash": Decimal("30")},
    )
    aug = build_period_metrics(
        tb_id=uuid4(),
        period_end=date(2026, 8, 31),
        line_amounts={"revenue": Decimal("50"), "cash": Decimal("40")},
    )
    quarters = aggregate_performance_periods(
        [apr, may, jul, aug],
        granularity="quarterly",
        as_of=date(2026, 8, 31),
    )
    assert [q.bucket_key for q in quarters] == ["2026-Q2", "2026-Q3"]
    q2, q3 = quarters
    assert q2.metrics["revenue"] == Decimal("300.00")
    assert q3.metrics["revenue"] == Decimal("100.00")

    correct = growth_pct(q3.metrics["revenue"], q2.metrics["revenue"])
    wrong_vs_prior_month = growth_pct(q3.metrics["revenue"], may.metrics["revenue"])

    assert correct == Decimal("-66.7")
    assert wrong_vs_prior_month == Decimal("-50.0")
    assert correct != wrong_vs_prior_month

    # Contract for the UI: prior bucket is periods[i-1] after aggregation.
    assert growth_pct(
        quarters[1].metrics["revenue"],
        quarters[0].metrics["revenue"],
    ) == correct
