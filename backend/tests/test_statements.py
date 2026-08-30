"""Tests for SOPL and SOFP statement builder."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.services.statements import (
    MappedStatementAccount,
    build_sofp,
    build_sopl,
)


def _acct(
    code: str,
    *,
    net_balance: str,
    canonical_line: str,
    account_id: uuid.UUID | None = None,
) -> MappedStatementAccount:
    return MappedStatementAccount(
        id=account_id or uuid.uuid4(),
        account_code=code,
        net_balance=Decimal(net_balance),
        canonical_line=canonical_line,
    )


def _by_code(lines, code: str):
    matches = [line for line in lines if line.line_item_code == code]
    assert len(matches) == 1, f"expected one {code}, got {len(matches)}"
    return matches[0]


def test_sopl_groups_accounts_computes_subtotals_and_provenance() -> None:
    rev_a = _acct("4000", net_balance="-8000.00", canonical_line="revenue")
    rev_b = _acct("4100", net_balance="-2000.00", canonical_line="revenue")
    cos_a = _acct("5000", net_balance="3000.00", canonical_line="cost_of_sales")
    cos_b = _acct("5100", net_balance="1000.00", canonical_line="cost_of_sales")
    opex_a = _acct("6000", net_balance="1500.00", canonical_line="operating_expenses")
    opex_b = _acct("6100", net_balance="500.00", canonical_line="operating_expenses")
    dep_a = _acct("7000", net_balance="200.00", canonical_line="depreciation")
    dep_b = _acct("7100", net_balance="100.00", canonical_line="depreciation")
    int_inc_a = _acct("8000", net_balance="-50.00", canonical_line="interest_income")
    int_inc_b = _acct("8010", net_balance="-25.00", canonical_line="interest_income")
    int_exp_a = _acct("8100", net_balance="40.00", canonical_line="interest_expense")
    int_exp_b = _acct("8110", net_balance="10.00", canonical_line="interest_expense")
    tax_a = _acct("8200", net_balance="300.00", canonical_line="tax")
    tax_b = _acct("8210", net_balance="100.00", canonical_line="tax")

    lines = build_sopl(
        [
            rev_a,
            rev_b,
            cos_a,
            cos_b,
            opex_a,
            opex_b,
            dep_a,
            dep_b,
            int_inc_a,
            int_inc_b,
            int_exp_a,
            int_exp_b,
            tax_a,
            tax_b,
        ]
    )

    assert [line.line_item_code for line in lines] == [
        "revenue",
        "cost_of_sales",
        "gross_profit",
        "operating_expenses",
        "depreciation",
        "operating_profit",
        "interest_income",
        "interest_expense",
        "profit_before_tax",
        "tax",
        "net_profit",
    ]
    assert [line.display_order for line in lines] == list(range(1, 12))

    revenue = _by_code(lines, "revenue")
    assert revenue.amount == Decimal("10000.00")
    assert revenue.is_subtotal is False
    assert set(revenue.source_account_ids) == {rev_a.id, rev_b.id}

    cost_of_sales = _by_code(lines, "cost_of_sales")
    assert cost_of_sales.amount == Decimal("4000.00")
    assert set(cost_of_sales.source_account_ids) == {cos_a.id, cos_b.id}

    gross_profit = _by_code(lines, "gross_profit")
    assert gross_profit.amount == Decimal("6000.00")
    assert gross_profit.is_subtotal is True
    assert set(gross_profit.source_account_ids) == {
        rev_a.id,
        rev_b.id,
        cos_a.id,
        cos_b.id,
    }

    operating_expenses = _by_code(lines, "operating_expenses")
    assert operating_expenses.amount == Decimal("2000.00")

    depreciation = _by_code(lines, "depreciation")
    assert depreciation.amount == Decimal("300.00")
    assert depreciation.is_subtotal is False
    assert set(depreciation.source_account_ids) == {dep_a.id, dep_b.id}

    operating_profit = _by_code(lines, "operating_profit")
    # 6000 - 2000 opex - 300 depreciation
    assert operating_profit.amount == Decimal("3700.00")
    assert set(operating_profit.source_account_ids) >= {dep_a.id, dep_b.id}

    interest_income = _by_code(lines, "interest_income")
    assert interest_income.amount == Decimal("75.00")
    interest_expense = _by_code(lines, "interest_expense")
    assert interest_expense.amount == Decimal("50.00")

    profit_before_tax = _by_code(lines, "profit_before_tax")
    assert profit_before_tax.amount == Decimal("3725.00")

    tax = _by_code(lines, "tax")
    assert tax.amount == Decimal("400.00")

    net_profit = _by_code(lines, "net_profit")
    assert net_profit.amount == Decimal("3325.00")
    assert net_profit.is_subtotal is True


def test_sopl_depreciation_is_visible_face_line_and_reduces_operating_profit() -> None:
    """Depreciation is its own SOPL face line (Appendix A / C), not silent in OP."""
    rev = _acct("4000", net_balance="-10000.00", canonical_line="revenue")
    cos = _acct("5000", net_balance="4000.00", canonical_line="cost_of_sales")
    opex = _acct("6000", net_balance="2000.00", canonical_line="operating_expenses")
    dep = _acct("7000", net_balance="500.00", canonical_line="depreciation")

    lines = build_sopl([rev, cos, opex, dep])

    codes = [line.line_item_code for line in lines]
    assert codes.index("depreciation") == codes.index("operating_expenses") + 1
    assert codes.index("operating_profit") == codes.index("depreciation") + 1

    depreciation = _by_code(lines, "depreciation")
    assert depreciation.amount == Decimal("500.00")
    assert depreciation.is_subtotal is False
    assert depreciation.source_account_ids == [dep.id]
    assert depreciation.line_item_name == "Depreciation"

    gross_profit = _by_code(lines, "gross_profit")
    operating_expenses = _by_code(lines, "operating_expenses")
    operating_profit = _by_code(lines, "operating_profit")
    assert gross_profit.amount == Decimal("6000.00")
    assert operating_expenses.amount == Decimal("2000.00")
    assert operating_profit.amount == (
        gross_profit.amount - operating_expenses.amount - depreciation.amount
    )
    assert operating_profit.amount == Decimal("3500.00")
    assert dep.id in operating_profit.source_account_ids


def test_sofp_groups_accounts_computes_subtotals_and_provenance() -> None:
    ppe_a = _acct("1100", net_balance="4000.00", canonical_line="property_plant_equipment")
    ppe_b = _acct("1200", net_balance="1000.00", canonical_line="property_plant_equipment")
    intang_a = _acct("1300", net_balance="500.00", canonical_line="intangible_assets")
    intang_b = _acct("1310", net_balance="200.00", canonical_line="intangible_assets")
    inv_a = _acct("1400", net_balance="800.00", canonical_line="inventory")
    inv_b = _acct("1410", net_balance="200.00", canonical_line="inventory")
    recv_a = _acct("1500", net_balance="1500.00", canonical_line="trade_receivables")
    recv_b = _acct("1510", net_balance="500.00", canonical_line="trade_receivables")
    cash_a = _acct("1600", net_balance="2000.00", canonical_line="cash")
    cash_b = _acct("1610", net_balance="300.00", canonical_line="cash")
    pay_a = _acct("2100", net_balance="-1200.00", canonical_line="trade_payables")
    pay_b = _acct("2110", net_balance="-300.00", canonical_line="trade_payables")
    acc_a = _acct("2200", net_balance="-400.00", canonical_line="accruals")
    acc_b = _acct("2210", net_balance="-100.00", canonical_line="accruals")
    loan_a = _acct("2300", net_balance="-2000.00", canonical_line="loans")
    loan_b = _acct("2310", net_balance="-500.00", canonical_line="loans")
    sc_a = _acct("3000", net_balance="-3000.00", canonical_line="share_capital")
    sc_b = _acct("3010", net_balance="-1000.00", canonical_line="share_capital")
    re_a = _acct("3100", net_balance="-2500.00", canonical_line="retained_earnings")
    re_b = _acct("3110", net_balance="-500.00", canonical_line="retained_earnings")
    div_a = _acct("3200", net_balance="150.00", canonical_line="dividends")
    div_b = _acct("3210", net_balance="50.00", canonical_line="dividends")

    lines = build_sofp(
        [
            ppe_a,
            ppe_b,
            intang_a,
            intang_b,
            inv_a,
            inv_b,
            recv_a,
            recv_b,
            cash_a,
            cash_b,
            pay_a,
            pay_b,
            acc_a,
            acc_b,
            loan_a,
            loan_b,
            sc_a,
            sc_b,
            re_a,
            re_b,
            div_a,
            div_b,
        ]
    )

    assert [line.line_item_code for line in lines] == [
        "property_plant_equipment",
        "intangible_assets",
        "inventory",
        "trade_receivables",
        "cash",
        "total_assets",
        "trade_payables",
        "accruals",
        "loans",
        "total_liabilities",
        "share_capital",
        "retained_earnings",
        "dividends",
        "total_equity",
    ]

    assert _by_code(lines, "property_plant_equipment").amount == Decimal("5000.00")
    assert set(_by_code(lines, "property_plant_equipment").source_account_ids) == {
        ppe_a.id,
        ppe_b.id,
    }

    total_assets = _by_code(lines, "total_assets")
    assert total_assets.amount == Decimal("11000.00")
    assert total_assets.is_subtotal is True
    assert cash_a.id in total_assets.source_account_ids
    assert ppe_b.id in total_assets.source_account_ids

    assert _by_code(lines, "trade_payables").amount == Decimal("1500.00")
    total_liabilities = _by_code(lines, "total_liabilities")
    assert total_liabilities.amount == Decimal("4500.00")

    assert _by_code(lines, "share_capital").amount == Decimal("4000.00")
    assert _by_code(lines, "retained_earnings").amount == Decimal("3000.00")
    dividends = _by_code(lines, "dividends")
    assert dividends.amount == Decimal("200.00")
    assert dividends.is_subtotal is False
    assert set(dividends.source_account_ids) == {div_a.id, div_b.id}

    total_equity = _by_code(lines, "total_equity")
    assert total_equity.amount == Decimal("7000.00")
    assert total_equity.is_subtotal is True
    # Dividends shown separately; not folded into total_equity provenance or amount.
    assert div_a.id not in total_equity.source_account_ids
    assert div_b.id not in total_equity.source_account_ids
    assert set(total_equity.source_account_ids) == {sc_a.id, sc_b.id, re_a.id, re_b.id}


def test_sofp_total_equity_excludes_dividends_matching_validator_fixture() -> None:
    """Same dividends fixture as test_validator trigger-critical case.

    SC 5_000 + RE 3_000 = total_equity 8_000 (not 7_000 after dividends).
    """
    accounts = [
        _acct("1000", net_balance="10000.00", canonical_line="cash"),
        _acct("2000", net_balance="-3000.00", canonical_line="trade_payables"),
        _acct("3000", net_balance="-5000.00", canonical_line="share_capital"),
        _acct("3100", net_balance="-3000.00", canonical_line="retained_earnings"),
        _acct("3200", net_balance="1000.00", canonical_line="dividends"),
    ]

    lines = build_sofp(accounts)

    assert _by_code(lines, "cash").amount == Decimal("10000.00")
    assert _by_code(lines, "trade_payables").amount == Decimal("3000.00")
    assert _by_code(lines, "share_capital").amount == Decimal("5000.00")
    assert _by_code(lines, "retained_earnings").amount == Decimal("3000.00")
    assert _by_code(lines, "dividends").amount == Decimal("1000.00")

    total_equity = _by_code(lines, "total_equity")
    assert total_equity.amount == Decimal("8000.00")
    assert total_equity.is_subtotal is True
    for dividend_id in _by_code(lines, "dividends").source_account_ids:
        assert dividend_id not in total_equity.source_account_ids
