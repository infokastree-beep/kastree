"""Tests for SOPL and SOFP statement builder."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.services.statements import (
    EQUITY_COMPONENT_LINES,
    MappedStatementAccount,
    SocieSofpEquityMismatchError,
    _compute_socie_rollforward,
    build_socie,
    build_sofp,
    build_sopl,
    build_statements,
    compute_net_profit,
    compute_total_equity,
    face_amount_from_net_balance,
)
from app.services.validator import (
    SimpleMappedAccount,
    _total_equity_balance_sheet,
    _total_equity_sofp,
    validate_trial_balance,
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


def test_face_amount_from_net_balance_sign_convention() -> None:
    # Credit-normal revenue: credit TB → positive face.
    assert face_amount_from_net_balance("revenue", Decimal("-1000.00")) == Decimal(
        "1000.00"
    )
    # Debit-normal expense: debit TB → positive face.
    assert face_amount_from_net_balance(
        "operating_expenses", Decimal("250.00")
    ) == Decimal("250.00")
    # Debit-normal asset: debit TB → positive face.
    assert face_amount_from_net_balance("cash", Decimal("500.00")) == Decimal("500.00")


def test_sopl_groups_accounts_computes_subtotals_and_provenance() -> None:
    rev_a = _acct("4000", net_balance="-8000.00", canonical_line="revenue")
    rev_b = _acct("4100", net_balance="-2000.00", canonical_line="revenue")
    cos_a = _acct("5000", net_balance="3000.00", canonical_line="cost_of_sales")
    cos_b = _acct("5100", net_balance="1000.00", canonical_line="cost_of_sales")
    opex_a = _acct("6000", net_balance="1500.00", canonical_line="operating_expenses")
    opex_b = _acct("6100", net_balance="500.00", canonical_line="operating_expenses")
    dep_a = _acct("7000", net_balance="200.00", canonical_line="depreciation")
    amort_a = _acct("7100", net_balance="100.00", canonical_line="amortisation")
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
            amort_a,
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
        "amortisation",
        "operating_profit",
        "interest_income",
        "interest_expense",
        "profit_before_tax",
        "tax",
        "net_profit",
    ]
    assert [line.display_order for line in lines] == list(range(1, 13))

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
    assert depreciation.amount == Decimal("200.00")
    assert depreciation.is_subtotal is False
    assert set(depreciation.source_account_ids) == {dep_a.id}

    amortisation = _by_code(lines, "amortisation")
    assert amortisation.amount == Decimal("100.00")
    assert amortisation.is_subtotal is False
    assert set(amortisation.source_account_ids) == {amort_a.id}

    operating_profit = _by_code(lines, "operating_profit")
    # 6000 - 2000 opex - 200 depreciation - 100 amortisation
    assert operating_profit.amount == Decimal("3700.00")
    assert set(operating_profit.source_account_ids) >= {dep_a.id, amort_a.id}

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
    assert codes.index("amortisation") == codes.index("depreciation") + 1
    assert codes.index("operating_profit") == codes.index("amortisation") + 1

    depreciation = _by_code(lines, "depreciation")
    assert depreciation.amount == Decimal("500.00")
    assert depreciation.is_subtotal is False
    assert depreciation.source_account_ids == [dep.id]
    assert depreciation.line_item_name == "Depreciation"

    amortisation = _by_code(lines, "amortisation")
    assert amortisation.amount == Decimal("0.00")
    assert amortisation.line_item_name == "Amortisation"

    gross_profit = _by_code(lines, "gross_profit")
    operating_expenses = _by_code(lines, "operating_expenses")
    operating_profit = _by_code(lines, "operating_profit")
    assert gross_profit.amount == Decimal("6000.00")
    assert operating_expenses.amount == Decimal("2000.00")
    assert operating_profit.amount == (
        gross_profit.amount
        - operating_expenses.amount
        - depreciation.amount
        - amortisation.amount
    )
    assert operating_profit.amount == Decimal("3500.00")
    assert dep.id in operating_profit.source_account_ids


def test_sopl_amortisation_is_visible_face_line_and_reduces_operating_profit() -> None:
    """Amortisation is separate from depreciation on the SOPL face (Option A)."""
    rev = _acct("4000", net_balance="-10000.00", canonical_line="revenue")
    cos = _acct("5000", net_balance="4000.00", canonical_line="cost_of_sales")
    opex = _acct("6000", net_balance="2000.00", canonical_line="operating_expenses")
    dep = _acct("7000", net_balance="300.00", canonical_line="depreciation")
    amort = _acct("7100", net_balance="200.00", canonical_line="amortisation")

    lines = build_sopl([rev, cos, opex, dep, amort])

    amortisation = _by_code(lines, "amortisation")
    assert amortisation.amount == Decimal("200.00")
    assert amortisation.is_subtotal is False
    assert amortisation.source_account_ids == [amort.id]
    assert amortisation.line_item_name == "Amortisation"

    operating_profit = _by_code(lines, "operating_profit")
    assert operating_profit.amount == Decimal("3500.00")  # 6000 - 2000 - 300 - 200
    assert amort.id in operating_profit.source_account_ids
    assert compute_net_profit([rev, cos, opex, dep, amort]) == Decimal("3500.00")


def test_sofp_ppe_nets_accumulated_depreciation_contra_on_same_canonical_line() -> None:
    """Accumulated Depreciation mapped to PPE must reduce SOFP PPE (cost − accum)."""
    ppe_cost = _acct(
        "1400", net_balance="423500.00", canonical_line="property_plant_equipment"
    )
    accum_dep = _acct(
        "1450", net_balance="-107200.00", canonical_line="property_plant_equipment"
    )
    re = _acct("3100", net_balance="-1000.00", canonical_line="retained_earnings")
    sc = _acct("3000", net_balance="-315300.00", canonical_line="share_capital")

    sofp = build_sofp(
        [ppe_cost, accum_dep, re, sc],
        retained_earnings_closing=Decimal("1000.00"),
        retained_earnings_source_ids=[re.id],
    )
    ppe = _by_code(sofp, "property_plant_equipment")
    assert ppe.amount == Decimal("316300.00")
    assert set(ppe.source_account_ids) == {ppe_cost.id, accum_dep.id}


def test_sopl_depreciation_excludes_bs_contra_mapped_to_ppe() -> None:
    """Only P&L depreciation charges feed SOPL; BS contra on PPE must not."""
    rev = _acct("4000", net_balance="-100000.00", canonical_line="revenue")
    cos = _acct("5000", net_balance="40000.00", canonical_line="cost_of_sales")
    opex = _acct("6000", net_balance="10000.00", canonical_line="operating_expenses")
    dep_charge = _acct("7000", net_balance="46700.00", canonical_line="depreciation")
    accum_dep = _acct(
        "1450", net_balance="-107200.00", canonical_line="property_plant_equipment"
    )

    sopl = build_sopl([rev, cos, opex, dep_charge, accum_dep])
    depreciation = _by_code(sopl, "depreciation")
    assert depreciation.amount == Decimal("46700.00")
    assert depreciation.source_account_ids == [dep_charge.id]
    assert accum_dep.id not in depreciation.source_account_ids

    operating_profit = _by_code(sopl, "operating_profit")
    # 60000 GP − 10000 opex − 46700 dep = 3300
    assert operating_profit.amount == Decimal("3300.00")


def test_sofp_intangibles_nets_accumulated_amortisation_contra() -> None:
    """Accumulated Amortisation on intangible_assets reduces SOFP intangibles."""
    cost = _acct("1500", net_balance="39400.00", canonical_line="intangible_assets")
    accum = _acct("1550", net_balance="-5600.00", canonical_line="intangible_assets")
    re = _acct("3100", net_balance="-1000.00", canonical_line="retained_earnings")
    sc = _acct("3000", net_balance="-32800.00", canonical_line="share_capital")

    sofp = build_sofp(
        [cost, accum, re, sc],
        retained_earnings_closing=Decimal("1000.00"),
        retained_earnings_source_ids=[re.id],
    )
    intangibles = _by_code(sofp, "intangible_assets")
    assert intangibles.amount == Decimal("33800.00")
    assert set(intangibles.source_account_ids) == {cost.id, accum.id}


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

    accounts = [
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
    rollforward = _compute_socie_rollforward(accounts)
    lines = build_sofp(
        accounts,
        retained_earnings_closing=rollforward.retained_earnings_closing_amount,
        retained_earnings_source_ids=rollforward.retained_earnings_closing_ids,
    )

    assert [line.line_item_code for line in lines] == [
        "property_plant_equipment",
        "intangible_assets",
        "investments",
        "non_current_assets",
        "inventory",
        "trade_receivables",
        "prepayments",
        "accrued_income",
        "cash",
        "current_assets",
        "total_assets",
        "loans",
        "non_current_liabilities",
        "trade_payables",
        "provisions",
        "accruals",
        "deferred_income",
        "taxes_payable",
        "social_security_payable",
        "current_liabilities",
        "total_liabilities",
        "share_capital",
        "share_premium",
        "retained_earnings",
        "revaluation_reserve",
        "dividends",
        "total_equity",
    ]

    assert _by_code(lines, "property_plant_equipment").amount == Decimal("5000.00")
    assert set(_by_code(lines, "property_plant_equipment").source_account_ids) == {
        ppe_a.id,
        ppe_b.id,
    }

    non_current_assets = _by_code(lines, "non_current_assets")
    # PPE 5000 + intangibles 700 + investments 0
    assert non_current_assets.amount == Decimal("5700.00")
    assert non_current_assets.is_subtotal is True
    assert non_current_assets.line_item_name == "Non-current assets"

    current_assets = _by_code(lines, "current_assets")
    # inventory 1000 + receivables 2000 + prepayments 0 + accrued_income 0 + cash 2300
    assert current_assets.amount == Decimal("5300.00")
    assert current_assets.is_subtotal is True
    assert current_assets.line_item_name == "Current assets"

    total_assets = _by_code(lines, "total_assets")
    assert total_assets.amount == Decimal("11000.00")
    assert total_assets.is_subtotal is True
    assert cash_a.id in total_assets.source_account_ids
    assert ppe_b.id in total_assets.source_account_ids

    assert _by_code(lines, "trade_payables").amount == Decimal("1500.00")

    non_current_liabilities = _by_code(lines, "non_current_liabilities")
    # loans 2500 (default NC classification)
    assert non_current_liabilities.amount == Decimal("2500.00")
    assert non_current_liabilities.is_subtotal is True
    assert non_current_liabilities.line_item_name == "Non-current liabilities"

    current_liabilities = _by_code(lines, "current_liabilities")
    # payables 1500 + provisions 0 + accruals 500 + deferred 0 + tax 0 + SS 0
    assert current_liabilities.amount == Decimal("2000.00")
    assert current_liabilities.is_subtotal is True
    assert current_liabilities.line_item_name == "Current liabilities"

    total_liabilities = _by_code(lines, "total_liabilities")
    assert total_liabilities.amount == Decimal("4500.00")
    assert total_liabilities.is_subtotal is True

    assert _by_code(lines, "share_capital").amount == Decimal("4000.00")
    # Zero P&L: closing RE = opening 3_000 − dividends 200 = 2_800.
    assert _by_code(lines, "retained_earnings").amount == Decimal("2800.00")
    dividends = _by_code(lines, "dividends")
    assert dividends.amount == Decimal("200.00")
    assert dividends.is_subtotal is False
    assert set(dividends.source_account_ids) == {div_a.id, div_b.id}

    total_equity = _by_code(lines, "total_equity")
    assert total_equity.amount == Decimal("6800.00")
    assert total_equity.is_subtotal is True
    # Closing RE provenance includes dividend accounts (they reduced closing RE);
    # total_equity is SC + closing RE only here (no share_premium / revaluation_reserve).
    assert set(total_equity.source_account_ids) == set(rollforward.total_equity_closing_ids)


def test_sofp_current_non_current_segmentation_golden_fixture() -> None:
    """Golden SOFP face order and section maths for NC / current split.

    Classification defaults (documented in statements.py): investments + loans →
    non-current; provisions → current. Section subtotals use intermediate
    ``is_subtotal`` styling codes (no ``total_`` prefix); grand totals keep
    ``total_assets`` / ``total_liabilities``.
    """
    ppe = _acct("1100", net_balance="10000.00", canonical_line="property_plant_equipment")
    intang = _acct("1200", net_balance="2000.00", canonical_line="intangible_assets")
    investments = _acct("1250", net_balance="1500.00", canonical_line="investments")
    inventory = _acct("1300", net_balance="800.00", canonical_line="inventory")
    receivables = _acct("1400", net_balance="1200.00", canonical_line="trade_receivables")
    prepayments = _acct("1450", net_balance="100.00", canonical_line="prepayments")
    accrued_income = _acct("1460", net_balance="50.00", canonical_line="accrued_income")
    cash = _acct("1500", net_balance="3000.00", canonical_line="cash")
    loans = _acct("2300", net_balance="-5000.00", canonical_line="loans")
    payables = _acct("2100", net_balance="-900.00", canonical_line="trade_payables")
    provisions = _acct("2150", net_balance="-300.00", canonical_line="provisions")
    accruals = _acct("2200", net_balance="-200.00", canonical_line="accruals")
    deferred = _acct("2210", net_balance="-100.00", canonical_line="deferred_income")
    tax_pay = _acct("2250", net_balance="-150.00", canonical_line="taxes_payable")
    ss_pay = _acct("2260", net_balance="-50.00", canonical_line="social_security_payable")
    sc = _acct("3000", net_balance="-7000.00", canonical_line="share_capital")
    re = _acct("3100", net_balance="-4950.00", canonical_line="retained_earnings")

    accounts = [
        ppe,
        intang,
        investments,
        inventory,
        receivables,
        prepayments,
        accrued_income,
        cash,
        loans,
        payables,
        provisions,
        accruals,
        deferred,
        tax_pay,
        ss_pay,
        sc,
        re,
    ]
    lines = build_sofp(
        accounts,
        retained_earnings_closing=Decimal("4950.00"),
        retained_earnings_source_ids=[re.id],
    )

    assert [line.line_item_code for line in lines] == [
        "property_plant_equipment",
        "intangible_assets",
        "investments",
        "non_current_assets",
        "inventory",
        "trade_receivables",
        "prepayments",
        "accrued_income",
        "cash",
        "current_assets",
        "total_assets",
        "loans",
        "non_current_liabilities",
        "trade_payables",
        "provisions",
        "accruals",
        "deferred_income",
        "taxes_payable",
        "social_security_payable",
        "current_liabilities",
        "total_liabilities",
        "share_capital",
        "share_premium",
        "retained_earnings",
        "revaluation_reserve",
        "dividends",
        "total_equity",
    ]

    assert _by_code(lines, "non_current_assets").amount == Decimal("13500.00")
    assert _by_code(lines, "current_assets").amount == Decimal("5150.00")
    assert _by_code(lines, "total_assets").amount == Decimal("18650.00")
    assert _by_code(lines, "non_current_liabilities").amount == Decimal("5000.00")
    assert _by_code(lines, "current_liabilities").amount == Decimal("1700.00")
    assert _by_code(lines, "total_liabilities").amount == Decimal("6700.00")
    assert _by_code(lines, "total_equity").amount == Decimal("11950.00")  # 7000 + 4950

    for code in (
        "non_current_assets",
        "current_assets",
        "total_assets",
        "non_current_liabilities",
        "current_liabilities",
        "total_liabilities",
        "total_equity",
    ):
        assert _by_code(lines, code).is_subtotal is True

    # Section maths reconcile to grands.
    assert (
        _by_code(lines, "non_current_assets").amount
        + _by_code(lines, "current_assets").amount
        == _by_code(lines, "total_assets").amount
    )
    assert (
        _by_code(lines, "non_current_liabilities").amount
        + _by_code(lines, "current_liabilities").amount
        == _by_code(lines, "total_liabilities").amount
    )

    # Default classification: loans before current liability leaves; provisions
    # sit in the current block (after loans section subtotal).
    codes = [line.line_item_code for line in lines]
    assert codes.index("loans") < codes.index("non_current_liabilities")
    assert codes.index("non_current_liabilities") < codes.index("provisions")
    assert codes.index("provisions") < codes.index("current_liabilities")


def test_sofp_total_equity_excludes_dividends_matching_validator_fixture() -> None:
    """SOFP with opening RE on face matches Check 4 when profit is zero.

    Validator Check 4 builds equity as SC + opening RE + profit (still excluding
    dividends). With zero P&L this fixture's Check 4 equity equals SOFP
    total_equity = SC 5_000 + opening RE 3_000 = 8_000 when closing RE is
    passed explicitly as the TB opening balance (no roll-forward deduction).
    """
    accounts = [
        _acct("1000", net_balance="10000.00", canonical_line="cash"),
        _acct("2000", net_balance="-3000.00", canonical_line="trade_payables"),
        _acct("3000", net_balance="-5000.00", canonical_line="share_capital"),
        _acct("3100", net_balance="-3000.00", canonical_line="retained_earnings"),
        _acct("3200", net_balance="1000.00", canonical_line="dividends"),
    ]
    re_account = accounts[3]

    lines = build_sofp(
        accounts,
        retained_earnings_closing=Decimal("3000.00"),
        retained_earnings_source_ids=[re_account.id],
    )

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


def test_socie_reconciles_with_sofp_on_dividends_fixture() -> None:
    """Trigger-critical dividends fixture with correct opening RE from current TB.

    Cash 10_000 | Payables 3_000 | SC 5_000 | RE 3_000 | Dividends 1_000.
    No P&L accounts → profit_for_period = 0.
    retained_earnings_opening = 3_000 (TB RE account, not zero).
    retained_earnings_closing = 3_000 + 0 − 1_000 = 2_000.
    total_equity_closing = 5_000 + 2_000 = 7_000 on both SOCIE and SOFP.

    Note: validator Check 4 still fails this fixture (equity 8_000 vs net assets
    7_000) because it excludes open dividends; SOCIE/SOFP closing path deducts
    them and therefore reconciles at 7_000.
    """
    accounts = [
        _acct("1000", net_balance="10000.00", canonical_line="cash"),
        _acct("2000", net_balance="-3000.00", canonical_line="trade_payables"),
        _acct("3000", net_balance="-5000.00", canonical_line="share_capital"),
        _acct("3100", net_balance="-3000.00", canonical_line="retained_earnings"),
        _acct("3200", net_balance="1000.00", canonical_line="dividends"),
    ]

    sopl_lines, sofp_lines, socie_lines = build_statements(accounts)

    assert [line.line_item_code for line in socie_lines] == [
        "retained_earnings_opening",
        "profit_for_period",
        "dividends",
        "retained_earnings_closing",
        "share_capital",
        "total_equity_closing",
    ]

    assert _by_code(socie_lines, "retained_earnings_opening").amount == Decimal("3000.00")
    assert _by_code(socie_lines, "profit_for_period").amount == Decimal("0.00")
    assert _by_code(socie_lines, "profit_for_period").amount == _by_code(
        sopl_lines, "net_profit"
    ).amount
    assert _by_code(socie_lines, "dividends").amount == Decimal("1000.00")
    assert _by_code(socie_lines, "dividends").amount == _by_code(
        sofp_lines, "dividends"
    ).amount
    assert set(_by_code(socie_lines, "dividends").source_account_ids) == set(
        _by_code(sofp_lines, "dividends").source_account_ids
    )

    re_closing = _by_code(socie_lines, "retained_earnings_closing")
    assert re_closing.amount == Decimal("2000.00")
    assert re_closing.is_subtotal is True
    assert re_closing.amount == _by_code(sofp_lines, "retained_earnings").amount

    assert _by_code(socie_lines, "share_capital").amount == Decimal("5000.00")

    total_equity_closing = _by_code(socie_lines, "total_equity_closing")
    assert total_equity_closing.amount == Decimal("7000.00")
    assert total_equity_closing.is_subtotal is True
    assert total_equity_closing.amount == _by_code(sofp_lines, "total_equity").amount


def test_socie_reconciles_with_sofp_when_share_premium_and_revaluation_reserve_present() -> None:
    """SOCIE total_equity_closing must include share_premium and revaluation_reserve.

    Regression: a two-component SC + closing RE formula would disagree with SOFP
    total_equity (SC + SP + closing RE + RR) and raise SocieSofpEquityMismatchError
    on otherwise correct data.
    """
    accounts = [
        _acct("1000", net_balance="10000.00", canonical_line="cash"),
        _acct("2000", net_balance="-3000.00", canonical_line="trade_payables"),
        _acct("3000", net_balance="-4000.00", canonical_line="share_capital"),
        _acct("3050", net_balance="-1000.00", canonical_line="share_premium"),
        _acct("3100", net_balance="-1500.00", canonical_line="retained_earnings"),
        _acct("3150", net_balance="-500.00", canonical_line="revaluation_reserve"),
    ]

    sopl_lines, sofp_lines, socie_lines = build_statements(accounts)

    assert _by_code(sofp_lines, "share_premium").amount == Decimal("1000.00")
    assert _by_code(sofp_lines, "revaluation_reserve").amount == Decimal("500.00")
    assert _by_code(sofp_lines, "total_equity").amount == Decimal("7000.00")

    total_equity_closing = _by_code(socie_lines, "total_equity_closing")
    assert total_equity_closing.amount == Decimal("7000.00")
    assert total_equity_closing.amount == _by_code(sofp_lines, "total_equity").amount


def test_compute_net_profit_matches_sopl_and_socie_profit_for_period() -> None:
    """Shared profit function is the single source for SOPL, SOCIE, and validator."""
    accounts = [
        _acct("1000", net_balance="12000.00", canonical_line="cash"),
        _acct("2000", net_balance="-3000.00", canonical_line="trade_payables"),
        _acct("3000", net_balance="-5000.00", canonical_line="share_capital"),
        _acct("3100", net_balance="-2000.00", canonical_line="retained_earnings"),
        _acct("4000", net_balance="-5000.00", canonical_line="revenue"),
        _acct("5000", net_balance="2000.00", canonical_line="cost_of_sales"),
        _acct("6000", net_balance="1000.00", canonical_line="operating_expenses"),
    ]
    profit = compute_net_profit(accounts)
    assert profit == Decimal("2000.00")

    sopl_lines, sofp_lines, socie_lines = build_statements(accounts)
    assert _by_code(sopl_lines, "net_profit").amount == profit
    assert _by_code(socie_lines, "profit_for_period").amount == profit
    # Closing RE = 2_000 opening + 2_000 profit − 0 dividends = 4_000
    assert _by_code(socie_lines, "retained_earnings_closing").amount == Decimal("4000.00")
    assert _by_code(sofp_lines, "retained_earnings").amount == Decimal("4000.00")
    assert _by_code(socie_lines, "total_equity_closing").amount == Decimal("9000.00")
    assert _by_code(sofp_lines, "total_equity").amount == Decimal("9000.00")


def test_socie_raises_when_total_equity_disagrees_with_sofp() -> None:
    """SOCIE closing equity (7_000) must not silently match a stale SOFP (8_000)."""
    accounts = [
        _acct("1000", net_balance="10000.00", canonical_line="cash"),
        _acct("2000", net_balance="-3000.00", canonical_line="trade_payables"),
        _acct("3000", net_balance="-5000.00", canonical_line="share_capital"),
        _acct("3100", net_balance="-3000.00", canonical_line="retained_earnings"),
        _acct("3200", net_balance="1000.00", canonical_line="dividends"),
    ]
    sopl_lines = build_sopl(accounts)
    # Deliberately pass opening RE as closing (8_000 total equity) while SOCIE
    # roll-forward deducts dividends and lands at 7_000.
    sofp_lines = build_sofp(
        accounts,
        retained_earnings_closing=Decimal("3000.00"),
        retained_earnings_source_ids=[accounts[3].id],
    )

    with pytest.raises(SocieSofpEquityMismatchError) as exc_info:
        build_socie(
            accounts,
            sopl_lines=sopl_lines,
            sofp_lines=sofp_lines,
        )

    assert exc_info.value.socie_total == Decimal("7000.00")
    assert exc_info.value.sofp_total == Decimal("8000.00")


def test_socie_opening_re_from_current_tb_not_prior_period() -> None:
    """Opening RE is the current TB retained_earnings balance, not prior-period TB."""
    current = [
        _acct("1000", net_balance="6500.00", canonical_line="cash"),
        _acct("3000", net_balance="-4000.00", canonical_line="share_capital"),
        _acct("3100", net_balance="-2500.00", canonical_line="retained_earnings"),
        _acct("3200", net_balance="500.00", canonical_line="dividends"),
        _acct("4000", net_balance="-1000.00", canonical_line="revenue"),
    ]
    # opening 2_500 (current TB) + profit 1_000 − dividends 500 = closing RE 3_000
    # total equity closing = 4_000 + 3_000 = 7_000

    sopl_lines, sofp_lines, socie_lines = build_statements(current)

    assert _by_code(socie_lines, "retained_earnings_opening").amount == Decimal("2500.00")
    assert _by_code(socie_lines, "profit_for_period").amount == Decimal("1000.00")
    assert _by_code(socie_lines, "dividends").amount == Decimal("500.00")
    assert _by_code(socie_lines, "retained_earnings_closing").amount == Decimal("3000.00")
    assert _by_code(socie_lines, "total_equity_closing").amount == Decimal("7000.00")
    assert _by_code(socie_lines, "total_equity_closing").amount == _by_code(
        sofp_lines, "total_equity"
    ).amount


def test_nil_face_lines_omitted_and_empty_sofp_section_subtotal_hidden() -> None:
    """Display filter hides nil leaves / empty SOFP sections; builders stay full."""
    from app.services.statements import filter_nil_face_lines

    accounts = [
        _acct("1500", net_balance="1000.00", canonical_line="cash"),
        _acct("2100", net_balance="-200.00", canonical_line="trade_payables"),
        _acct("3000", net_balance="-500.00", canonical_line="share_capital"),
        _acct("3100", net_balance="-300.00", canonical_line="retained_earnings"),
        _acct("4000", net_balance="-800.00", canonical_line="revenue"),
        _acct("5000", net_balance="200.00", canonical_line="cost_of_sales"),
    ]
    sopl_full, sofp_full, socie_full = build_statements(accounts)

    # Builders still emit the full skeleton (including zeros) for persistence.
    assert "amortisation" in [line.line_item_code for line in sopl_full]
    assert _by_code(sopl_full, "amortisation").amount == Decimal("0.00")
    assert "investments" in [line.line_item_code for line in sofp_full]
    assert _by_code(sofp_full, "investments").amount == Decimal("0.00")
    assert "non_current_liabilities" in [line.line_item_code for line in sofp_full]
    assert "profit_for_period" in [line.line_item_code for line in socie_full]

    sopl = filter_nil_face_lines(sopl_full)
    sofp = filter_nil_face_lines(sofp_full)
    socie = filter_nil_face_lines(socie_full)

    sopl_codes = [line.line_item_code for line in sopl]
    assert sopl_codes == [
        "revenue",
        "cost_of_sales",
        "gross_profit",
        "operating_profit",
        "profit_before_tax",
        "net_profit",
    ]
    assert "operating_expenses" not in sopl_codes
    assert "depreciation" not in sopl_codes
    assert "amortisation" not in sopl_codes
    assert "interest_income" not in sopl_codes
    assert "tax" not in sopl_codes
    assert _by_code(sopl, "net_profit").amount == Decimal("600.00")

    sofp_codes = [line.line_item_code for line in sofp]
    assert sofp_codes == [
        "cash",
        "current_assets",
        "total_assets",
        "trade_payables",
        "current_liabilities",
        "total_liabilities",
        "share_capital",
        "retained_earnings",
        "total_equity",
    ]
    assert "non_current_assets" not in sofp_codes
    assert "non_current_liabilities" not in sofp_codes
    assert "investments" not in sofp_codes
    assert "loans" not in sofp_codes
    assert "share_premium" not in sofp_codes
    assert _by_code(sofp, "total_assets").amount == Decimal("1000.00")
    assert _by_code(sofp, "total_liabilities").amount == Decimal("200.00")
    assert _by_code(sofp, "retained_earnings").amount == Decimal("900.00")
    assert _by_code(sofp, "total_equity").amount == Decimal("1400.00")

    socie_codes = [line.line_item_code for line in socie]
    assert socie_codes == [
        "retained_earnings_opening",
        "profit_for_period",
        "retained_earnings_closing",
        "share_capital",
        "total_equity_closing",
    ]
    assert "dividends" not in socie_codes
    assert _by_code(socie, "total_equity_closing").amount == Decimal("1400.00")


def test_compute_total_equity_sums_every_equity_component_line() -> None:
    """Shared helper is the only place that defines the equity-total sum."""
    amounts = {
        "share_capital": Decimal("2000.00"),
        "share_premium": Decimal("1000.00"),
        "retained_earnings": Decimal("5500.00"),
        "revaluation_reserve": Decimal("500.00"),
        "dividends": Decimal("999.00"),  # must be ignored
    }
    assert compute_total_equity(amounts) == Decimal("9000.00")
    assert compute_total_equity({}) == Decimal("0")
    assert set(EQUITY_COMPONENT_LINES) == {
        "share_capital",
        "share_premium",
        "retained_earnings",
        "revaluation_reserve",
    }


def test_four_equity_total_sites_all_call_compute_total_equity() -> None:
    """Structural guard: the four historical drift sites share one call.

    net_assets, balance_sheet_balance, build_sofp, and build_socie (via
    ``_compute_socie_rollforward``) each used to hand-sum equity components.
    Missing a new line in any one copy was the recurring bug class. After the
    refactor every site must call ``compute_total_equity``.
    """
    import ast
    import inspect

    import app.services.statements as statements_mod
    import app.services.validator as validator_mod

    def _calls_compute_total_equity(fn: object) -> bool:
        tree = ast.parse(inspect.getsource(fn))  # type: ignore[arg-type]
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "compute_total_equity":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "compute_total_equity":
                return True
        return False

    assert _calls_compute_total_equity(statements_mod.build_sofp)
    assert _calls_compute_total_equity(statements_mod._compute_socie_rollforward)
    assert _calls_compute_total_equity(validator_mod._total_equity_sofp)
    assert _calls_compute_total_equity(validator_mod._total_equity_balance_sheet)


def test_new_equity_canonical_line_cannot_diverge_across_four_call_sites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extending EQUITY_COMPONENT_LINES alone must update all four totals.

    This is the test that would have caught all four historical bugs at once:
    when a new equity face line (e.g. share_premium / revaluation_reserve) is
    added to the shared tuple, SOFP total_equity, SOCIE total_equity_closing,
    validator net_assets, and balance_sheet_balance must all include it —
    because they all derive from ``compute_total_equity`` / that tuple.
    """
    import app.services.statements as statements_mod
    import app.services.validator as validator_mod

    new_lines = statements_mod.EQUITY_COMPONENT_LINES + ("other_reserves",)
    monkeypatch.setattr(statements_mod, "EQUITY_COMPONENT_LINES", new_lines)
    monkeypatch.setattr(
        statements_mod, "SOFP_EQUITY_TOTAL_LINES", frozenset(new_lines)
    )
    monkeypatch.setattr(validator_mod, "EQUITY_COMPONENT_LINES", new_lines)
    monkeypatch.setattr(validator_mod, "EQUITY_LINES_SOFP", frozenset(new_lines))
    monkeypatch.setitem(
        statements_mod.LINE_ITEM_NAMES, "other_reserves", "Other reserves"
    )

    # Assets 10_000 − liabilities 2_000 = net assets 8_000.
    # Components: SC 3_000 + other_reserves 400 + opening RE 2_600 = 6_000
    # + period profit 2_000 → closing equity 8_000 (with other_reserves).
    # Without other_reserves the four sites would land at 7_600 and disagree
    # with net assets — the exact historical drift pattern.
    statement_accounts = [
        _acct("1000", net_balance="10000.00", canonical_line="cash"),
        _acct("2000", net_balance="-2000.00", canonical_line="trade_payables"),
        _acct("3000", net_balance="-3000.00", canonical_line="share_capital"),
        _acct("3300", net_balance="-400.00", canonical_line="other_reserves"),
        _acct("3100", net_balance="-2600.00", canonical_line="retained_earnings"),
        _acct("4000", net_balance="-2000.00", canonical_line="revenue"),
    ]

    _sopl, sofp_lines, socie_lines = build_statements(statement_accounts)

    assert _by_code(sofp_lines, "other_reserves").amount == Decimal("400.00")
    sofp_total = _by_code(sofp_lines, "total_equity").amount
    socie_total = _by_code(socie_lines, "total_equity_closing").amount
    assert sofp_total == Decimal("8000.00")
    assert socie_total == Decimal("8000.00")
    assert sofp_total == socie_total

    shared = compute_total_equity(
        {
            "share_capital": Decimal("3000.00"),
            "share_premium": Decimal("0"),
            "retained_earnings": Decimal("4600.00"),  # 2600 opening + 2000 profit
            "revaluation_reserve": Decimal("0"),
            "other_reserves": Decimal("400.00"),
        }
    )
    assert shared == Decimal("8000.00")
    assert shared == sofp_total == socie_total

    mapped = [
        SimpleMappedAccount(
            account_code=a.account_code,
            account_name=a.account_code,
            debit=a.net_balance if a.net_balance >= 0 else Decimal("0"),
            credit=(-a.net_balance) if a.net_balance < 0 else Decimal("0"),
            net_balance=a.net_balance,
            canonical_line=a.canonical_line,
        )
        for a in statement_accounts
    ]
    # Validator Check 4 equity (components + profit) and Check 2 (same, + dividends)
    # must both include other_reserves via the shared helper.
    assert _total_equity_sofp(mapped) == Decimal("8000.00")
    assert _total_equity_balance_sheet(mapped) == Decimal("8000.00")

    results = validate_trial_balance(mapped)
    assert _by_name_check(results, "net_assets").passed is True
    assert _by_name_check(results, "balance_sheet_balance").passed is True


def _by_name_check(results, check_name: str):
    matches = [c for c in results.checks if c.check_name == check_name]
    assert len(matches) == 1, f"expected one {check_name}, got {len(matches)}"
    return matches[0]
