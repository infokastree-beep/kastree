"""Unit tests for ISA 320-style materiality auto-suggestion."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.services.materiality import suggest_materiality


def _line(code: str, amount: str) -> SimpleNamespace:
    return SimpleNamespace(line_item_code=code, amount=Decimal(amount))


def test_trading_mid_range_suggestion_from_pbt() -> None:
    result = suggest_materiality(
        company_type="trading",
        current_pct=Decimal("10.00"),
        current_abs=Decimal("1000.00"),
        sopl_lines=[_line("profit_before_tax", "166000.00")],
        sofp_lines=[_line("total_equity", "500000.00")],
        dismissed=False,
    )
    assert result.available is True
    assert result.benchmark_basis == "profit_before_tax"
    assert result.suggested_pct == Decimal("7.50")
    # 7.5% of 166000 = 12450
    assert result.suggested_abs == Decimal("12450.00")
    assert result.message is not None
    assert "7.50%" in result.message


def test_holding_mid_range_suggestion_from_equity() -> None:
    result = suggest_materiality(
        company_type="holding",
        current_pct=Decimal("10.00"),
        current_abs=Decimal("1000.00"),
        sopl_lines=[_line("profit_before_tax", "10000.00")],
        sofp_lines=[_line("total_equity", "200000.00")],
        dismissed=False,
    )
    assert result.available is True
    assert result.benchmark_basis == "total_equity"
    assert result.suggested_pct == Decimal("6.50")
    # 6.5% of 200000 = 13000
    assert result.suggested_abs == Decimal("13000.00")


def test_unavailable_when_dismissed() -> None:
    result = suggest_materiality(
        company_type="trading",
        current_pct=Decimal("10.00"),
        current_abs=Decimal("1000.00"),
        sopl_lines=[_line("profit_before_tax", "166000.00")],
        sofp_lines=[],
        dismissed=True,
    )
    assert result.available is False
    assert result.dismissed is True
    assert result.suggested_pct == Decimal("7.50")


def test_unavailable_when_already_matches() -> None:
    result = suggest_materiality(
        company_type="trading",
        current_pct=Decimal("7.50"),
        current_abs=Decimal("12450.00"),
        sopl_lines=[_line("profit_before_tax", "166000.00")],
        sofp_lines=[],
        dismissed=False,
    )
    assert result.available is False
    assert result.suggested_pct == Decimal("7.50")
    assert "already matches" in (result.message or "")


def test_unavailable_when_pbt_nil() -> None:
    result = suggest_materiality(
        company_type="trading",
        current_pct=Decimal("10.00"),
        current_abs=Decimal("1000.00"),
        sopl_lines=[_line("profit_before_tax", "0.00")],
        sofp_lines=[],
        dismissed=False,
    )
    assert result.available is False
    assert result.suggested_pct is None
    assert "nil" in (result.message or "").lower()
