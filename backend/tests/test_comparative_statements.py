"""Unit tests for comparative current+prior statement face merge."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.services.comparative_statements import merge_comparative_face_lines
from app.services.statements import SOFP_FACE_ORDER, SOCIE_FACE_ORDER


def _line(
    code: str,
    amount: str,
    *,
    name: str | None = None,
    is_subtotal: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        line_item_code=code,
        line_item_name=name or code.replace("_", " ").title(),
        amount=Decimal(amount),
        is_subtotal=is_subtotal,
        source_account_ids=[],
    )


def test_merge_emdash_when_line_missing_on_either_side() -> None:
    current = [
        _line("revenue", "100.00"),
        _line("gross_profit", "100.00", is_subtotal=True),
        _line("net_profit", "80.00", is_subtotal=True),
    ]
    prior = [
        _line("revenue", "90.00"),
        _line("cost_of_sales", "10.00"),  # current-only missing → prior has it
        _line("gross_profit", "80.00", is_subtotal=True),
        _line("net_profit", "70.00", is_subtotal=True),
    ]
    # Current has amortisation-less face; invent a current-only leaf via revenue-only
    # and a prior-only cost_of_sales.
    merged = merge_comparative_face_lines("SOPL", current, prior)
    by_code = {line.line_item_code: line for line in merged}

    assert by_code["revenue"].amount == "100.00"
    assert by_code["revenue"].prior_amount == "90.00"
    assert by_code["cost_of_sales"].amount is None  # em dash on current
    assert by_code["cost_of_sales"].prior_amount == "10.00"
    assert "amortisation" not in by_code  # absent on both → omitted


def test_sofp_merge_preserves_nc_current_segmentation_order() -> None:
    """Both columns follow the same NC → current section spine."""
    current = [
        _line("property_plant_equipment", "500.00"),
        _line("non_current_assets", "500.00", is_subtotal=True),
        _line("cash", "50.00"),
        _line("current_assets", "50.00", is_subtotal=True),
        _line("total_assets", "550.00", is_subtotal=True),
        _line("loans", "100.00"),
        _line("non_current_liabilities", "100.00", is_subtotal=True),
        _line("trade_payables", "20.00"),
        _line("current_liabilities", "20.00", is_subtotal=True),
        _line("total_liabilities", "120.00", is_subtotal=True),
        _line("share_capital", "10.00"),
        _line("retained_earnings", "420.00"),
        _line("total_equity", "430.00", is_subtotal=True),
    ]
    # Prior has intangibles (NC) that current lacks, and no loans.
    prior = [
        _line("property_plant_equipment", "400.00"),
        _line("intangible_assets", "25.00"),
        _line("non_current_assets", "425.00", is_subtotal=True),
        _line("cash", "40.00"),
        _line("current_assets", "40.00", is_subtotal=True),
        _line("total_assets", "465.00", is_subtotal=True),
        _line("trade_payables", "15.00"),
        _line("current_liabilities", "15.00", is_subtotal=True),
        _line("total_liabilities", "15.00", is_subtotal=True),
        _line("share_capital", "10.00"),
        _line("retained_earnings", "440.00"),
        _line("total_equity", "450.00", is_subtotal=True),
    ]

    merged = merge_comparative_face_lines("SOFP", current, prior)
    codes = [line.line_item_code for line in merged]

    # Order must respect SOFP_FACE_ORDER subsequence.
    order_index = {code: i for i, code in enumerate(SOFP_FACE_ORDER)}
    positions = [order_index[code] for code in codes]
    assert positions == sorted(positions)

    # NC assets appear before current assets section.
    assert codes.index("property_plant_equipment") < codes.index("non_current_assets")
    assert codes.index("intangible_assets") < codes.index("non_current_assets")
    assert codes.index("non_current_assets") < codes.index("cash")
    assert codes.index("cash") < codes.index("current_assets")

    by_code = {line.line_item_code: line for line in merged}
    assert by_code["intangible_assets"].amount is None
    assert by_code["intangible_assets"].prior_amount == "25.00"
    assert by_code["loans"].amount == "100.00"
    assert by_code["loans"].prior_amount is None
    assert by_code["non_current_assets"].amount == "500.00"
    assert by_code["non_current_assets"].prior_amount == "425.00"


def test_socie_merge_two_independent_rollforwards() -> None:
    """S1: each column is that period's own opening/profit/dividends/closing."""
    current = [
        _line("retained_earnings_opening", "100.00"),
        _line("profit_for_period", "40.00"),
        _line("dividends", "10.00"),
        _line("retained_earnings_closing", "130.00", is_subtotal=True),
        _line("share_capital", "50.00"),
        _line("total_equity_closing", "180.00", is_subtotal=True),
    ]
    prior = [
        _line("retained_earnings_opening", "70.00"),
        _line("profit_for_period", "35.00"),
        _line("dividends", "5.00"),
        _line("retained_earnings_closing", "100.00", is_subtotal=True),
        _line("share_capital", "50.00"),
        _line("total_equity_closing", "150.00", is_subtotal=True),
    ]

    merged = merge_comparative_face_lines("SOCIE", current, prior)
    assert [line.line_item_code for line in merged] == list(SOCIE_FACE_ORDER)

    by_code = {line.line_item_code: line for line in merged}
    # Independent openings — NOT prior closing stuffed into current opening.
    assert by_code["retained_earnings_opening"].amount == "100.00"
    assert by_code["retained_earnings_opening"].prior_amount == "70.00"
    assert by_code["retained_earnings_closing"].amount == "130.00"
    assert by_code["retained_earnings_closing"].prior_amount == "100.00"
    assert by_code["profit_for_period"].amount == "40.00"
    assert by_code["profit_for_period"].prior_amount == "35.00"
