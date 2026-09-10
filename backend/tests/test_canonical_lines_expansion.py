"""Canonical lines expansion — granular Option A lines + accruals restore migration."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.account_mapping import AccountMapping
from app.services.llm import MAPPING_TIE_BREAKER_CANONICAL_LINES
from app.services.mapper import MappingResult, _parse_llm_mappings
from app.services.statements import (
    PROFIT_AND_LOSS_LINES,
    MappedStatementAccount,
    SOFP_ASSET_ORDER,
    SOFP_LIABILITY_ORDER,
    build_sofp,
    build_sopl,
    compute_net_profit,
)
from app.services.validator import ASSET_LINES, EQUITY_LINES_SOFP, LIABILITY_LINES

# Balance-sheet / equity expansion lines (excludes amortisation / other_revenue — P&L).
NEW_BALANCE_SHEET_LINES: tuple[str, ...] = (
    "investments",
    "prepayments",
    "accrued_income",
    "other_receivables",
    "other_payables",
    "provisions",
    "deferred_income",
    "taxes_payable",
    "social_security_payable",
    "share_premium",
    "capital_contribution",
    "revaluation_reserve",
)

NEW_CANONICAL_LINES: tuple[str, ...] = NEW_BALANCE_SHEET_LINES + (
    "amortisation",
    "other_revenue",
)

WITHDRAWN_COMBINED_LINES: tuple[str, ...] = (
    "prepayments_and_accrued_income",
    "accruals_and_deferred_income",
    "taxation_and_social_security",
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


def _by_code(lines: list, code: str):
    return next(line for line in lines if line.line_item_code == code)


@pytest.mark.parametrize("line", NEW_CANONICAL_LINES)
def test_new_canonical_lines_in_llm_allowlist(line: str) -> None:
    assert line in MAPPING_TIE_BREAKER_CANONICAL_LINES


@pytest.mark.parametrize("line", NEW_BALANCE_SHEET_LINES)
def test_new_canonical_lines_not_in_profit_and_loss_lines(line: str) -> None:
    assert line not in PROFIT_AND_LOSS_LINES


@pytest.mark.parametrize("line", WITHDRAWN_COMBINED_LINES)
def test_withdrawn_combined_lines_not_in_llm_allowlist(line: str) -> None:
    assert line not in MAPPING_TIE_BREAKER_CANONICAL_LINES


def test_accruals_restored_and_deferred_income_separate() -> None:
    assert "accruals" in MAPPING_TIE_BREAKER_CANONICAL_LINES
    assert "deferred_income" in MAPPING_TIE_BREAKER_CANONICAL_LINES
    assert "accruals_and_deferred_income" not in MAPPING_TIE_BREAKER_CANONICAL_LINES


def test_sofp_display_order_includes_split_lines() -> None:
    assert SOFP_ASSET_ORDER == (
        "property_plant_equipment",
        "intangible_assets",
        "investments",
        "inventory",
        "trade_receivables",
        "other_receivables",
        "prepayments",
        "accrued_income",
        "cash",
    )
    assert SOFP_LIABILITY_ORDER == (
        "loans",
        "trade_payables",
        "other_payables",
        "provisions",
        "accruals",
        "deferred_income",
        "taxes_payable",
        "social_security_payable",
    )


def test_validator_line_sets_include_split_balance_sheet_lines() -> None:
    assert "investments" in ASSET_LINES
    assert "prepayments" in ASSET_LINES
    assert "accrued_income" in ASSET_LINES
    assert "provisions" in LIABILITY_LINES
    assert "accruals" in LIABILITY_LINES
    assert "deferred_income" in LIABILITY_LINES
    assert "taxes_payable" in LIABILITY_LINES
    assert "social_security_payable" in LIABILITY_LINES
    assert "share_premium" in EQUITY_LINES_SOFP
    assert "capital_contribution" in EQUITY_LINES_SOFP
    assert "revaluation_reserve" in EQUITY_LINES_SOFP
    for withdrawn in WITHDRAWN_COMBINED_LINES:
        assert withdrawn not in ASSET_LINES
        assert withdrawn not in LIABILITY_LINES


@pytest.mark.parametrize("line", NEW_CANONICAL_LINES + ("accruals",))
def test_mapper_parse_llm_mappings_accepts_granular_canonical_lines(line: str) -> None:
    unmapped = [
        MappingResult(
            source_code="9999",
            source_name=f"Test {line}",
            canonical_line=None,
            confidence=None,
            method=None,
        )
    ]
    payload = {
        "mappings": [
            {
                "index": 1,
                "canonical_line": line,
                "reasoning": "Test mapping",
                "confidence": 0.87,
            }
        ]
    }
    results = _parse_llm_mappings(unmapped, payload)
    assert results[0].canonical_line == line
    assert results[0].method == "llm"
    assert results[0].confidence == Decimal("0.87")


def test_sofp_places_split_lines_in_expected_positions() -> None:
    re_id = uuid.uuid4()
    accounts = [
        _acct("1100", net_balance="1000.00", canonical_line="property_plant_equipment"),
        _acct("1200", net_balance="500.00", canonical_line="intangible_assets"),
        _acct("1250", net_balance="800.00", canonical_line="investments"),
        _acct("1300", net_balance="200.00", canonical_line="inventory"),
        _acct("1400", net_balance="300.00", canonical_line="trade_receivables"),
        _acct("1420", net_balance="150.00", canonical_line="other_receivables"),
        _acct("1450", net_balance="100.00", canonical_line="prepayments"),
        _acct("1460", net_balance="50.00", canonical_line="accrued_income"),
        _acct("1500", net_balance="250.00", canonical_line="cash"),
        _acct("2100", net_balance="-400.00", canonical_line="trade_payables"),
        _acct("2120", net_balance="-80.00", canonical_line="other_payables"),
        _acct("2150", net_balance="-100.00", canonical_line="provisions"),
        _acct("2200", net_balance="-40.00", canonical_line="accruals"),
        _acct("2210", net_balance="-10.00", canonical_line="deferred_income"),
        _acct("2250", net_balance="-50.00", canonical_line="taxes_payable"),
        _acct("2260", net_balance="-25.00", canonical_line="social_security_payable"),
        _acct("2300", net_balance="-500.00", canonical_line="loans"),
        _acct("3000", net_balance="-1000.00", canonical_line="share_capital"),
        _acct("3050", net_balance="-200.00", canonical_line="share_premium"),
        _acct("3070", net_balance="-75.00", canonical_line="capital_contribution"),
        _acct("3100", net_balance="-600.00", canonical_line="retained_earnings", account_id=re_id),
        _acct("3150", net_balance="-150.00", canonical_line="revaluation_reserve"),
    ]

    lines = build_sofp(
        accounts,
        retained_earnings_closing=Decimal("600.00"),
        retained_earnings_source_ids=[re_id],
    )

    codes = [line.line_item_code for line in lines]
    assert codes.index("investments") < codes.index("inventory")
    assert codes.index("other_receivables") > codes.index("trade_receivables")
    assert codes.index("prepayments") > codes.index("other_receivables")
    assert codes.index("accrued_income") > codes.index("prepayments")
    assert codes.index("non_current_assets") < codes.index("current_assets")
    assert codes.index("current_assets") < codes.index("total_assets")
    assert codes.index("loans") < codes.index("trade_payables")
    assert codes.index("other_payables") > codes.index("trade_payables")
    assert codes.index("provisions") > codes.index("other_payables")
    assert codes.index("deferred_income") > codes.index("accruals")
    assert codes.index("taxes_payable") > codes.index("deferred_income")
    assert codes.index("social_security_payable") > codes.index("taxes_payable")
    assert codes.index("non_current_liabilities") < codes.index("current_liabilities")
    assert codes.index("current_liabilities") < codes.index("total_liabilities")
    assert codes.index("share_premium") > codes.index("share_capital")
    assert codes.index("capital_contribution") > codes.index("share_premium")
    assert codes.index("retained_earnings") > codes.index("capital_contribution")
    assert codes.index("revaluation_reserve") > codes.index("retained_earnings")

    assert next(line for line in lines if line.line_item_code == "non_current_assets").amount == Decimal(
        "2300.00"
    )  # 1000 + 500 + 800
    assert next(line for line in lines if line.line_item_code == "current_assets").amount == Decimal(
        "1050.00"
    )  # 200 + 300 + 150 + 100 + 50 + 250
    assert next(
        line for line in lines if line.line_item_code == "non_current_liabilities"
    ).amount == Decimal("500.00")  # loans
    assert next(
        line for line in lines if line.line_item_code == "current_liabilities"
    ).amount == Decimal("705.00")  # 400 + 80 + 100 + 40 + 10 + 50 + 25

    total_equity = next(line for line in lines if line.line_item_code == "total_equity")
    assert total_equity.amount == Decimal("2025.00")  # 1000 + 200 + 75 + 600 + 150


def test_compute_net_profit_unchanged_by_new_balance_sheet_lines() -> None:
    accounts = [
        _acct("4000", net_balance="-1000.00", canonical_line="revenue"),
        _acct("5000", net_balance="400.00", canonical_line="cost_of_sales"),
        _acct("1250", net_balance="800.00", canonical_line="investments"),
        _acct("3050", net_balance="-200.00", canonical_line="share_premium"),
        _acct("1450", net_balance="50.00", canonical_line="prepayments"),
        _acct("2260", net_balance="-25.00", canonical_line="social_security_payable"),
    ]
    assert compute_net_profit(accounts) == Decimal("600.00")


def test_other_revenue_included_in_gross_profit() -> None:
    accounts = [
        _acct("4000", net_balance="-1000.00", canonical_line="revenue"),
        _acct("4100", net_balance="-50.00", canonical_line="other_revenue"),
        _acct("5000", net_balance="400.00", canonical_line="cost_of_sales"),
    ]
    lines = build_sopl(accounts)
    assert _by_code(lines, "other_revenue").amount == Decimal("50.00")
    assert _by_code(lines, "gross_profit").amount == Decimal("650.00")
    assert compute_net_profit(accounts) == Decimal("650.00")


def test_other_receivables_face_line_on_sofp() -> None:
    vat = _acct("1800", net_balance="120.00", canonical_line="other_receivables")
    cash = _acct("1500", net_balance="880.00", canonical_line="cash")
    sc = _acct("3000", net_balance="-1000.00", canonical_line="share_capital")
    lines = build_sofp(
        [vat, cash, sc],
        retained_earnings_closing=Decimal("0.00"),
        retained_earnings_source_ids=[],
    )
    codes = [line.line_item_code for line in lines]
    assert "trade_receivables" not in codes or codes.index("other_receivables") > codes.index(
        "trade_receivables"
    )
    assert codes.index("other_receivables") < codes.index("cash")
    assert _by_code(lines, "other_receivables").amount == Decimal("120.00")
    assert _by_code(lines, "current_assets").amount == Decimal("1000.00")


def test_validator_line_sets_include_misc_canonical_lines() -> None:
    assert "other_receivables" in ASSET_LINES
    assert "other_payables" in LIABILITY_LINES
    assert "other_revenue" in PROFIT_AND_LOSS_LINES
    assert "other_revenue" not in ASSET_LINES
    assert "other_revenue" not in LIABILITY_LINES


def test_amortisation_migration_remaps_named_rows_without_touching_depreciation(
    provisioned_org: dict,
) -> None:
    """Data migration SQL: depreciation rows whose source_name mentions amort*."""
    org_id = provisioned_org["org_id"]
    amort_id = uuid.uuid4()
    dep_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            AccountMapping(
                id=amort_id,
                company_id=provisioned_org["company_id"],
                source_code="7100",
                source_name="Amortisation - Software",
                canonical_line="depreciation",
                method="manual",
                is_confirmed=True,
            )
        )
        session.add(
            AccountMapping(
                id=dep_id,
                company_id=provisioned_org["company_id"],
                source_code="7000",
                source_name="Depreciation - Buildings",
                canonical_line="depreciation",
                method="manual",
                is_confirmed=True,
            )
        )
        session.commit()
        # SET LOCAL is transaction-scoped; re-apply after commit before RLS DML.
        set_rls_org_id(session, org_id)

        session.execute(
            text(
                """
                UPDATE account_mappings
                SET canonical_line = 'amortisation'
                WHERE canonical_line = 'depreciation'
                  AND source_name ILIKE '%amort%'
                """
            )
        )
        session.commit()
        set_rls_org_id(session, org_id)
        # Raw SQL bypasses the ORM; expire so subsequent SELECTs reload from DB.
        session.expire_all()

        amort = session.execute(
            select(AccountMapping).where(AccountMapping.id == amort_id)
        ).scalar_one()
        dep = session.execute(
            select(AccountMapping).where(AccountMapping.id == dep_id)
        ).scalar_one()
        assert amort.canonical_line == "amortisation"
        assert amort.source_name == "Amortisation - Software"
        assert dep.canonical_line == "depreciation"
        assert dep.source_name == "Depreciation - Buildings"


def test_option_a_migration_restores_accruals_without_data_loss(
    provisioned_org: dict,
) -> None:
    """Data migration SQL: accruals_and_deferred_income -> accruals."""
    org_id = provisioned_org["org_id"]
    row_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            AccountMapping(
                id=row_id,
                company_id=provisioned_org["company_id"],
                source_code="2100",
                source_name="Accruals",
                canonical_line="accruals_and_deferred_income",
                method="manual",
                is_confirmed=True,
            )
        )
        session.commit()
        # SET LOCAL is transaction-scoped; re-apply after commit before RLS DML/SELECT.
        set_rls_org_id(session, org_id)

        before = session.execute(
            select(AccountMapping).where(AccountMapping.id == row_id)
        ).scalar_one()
        assert before.canonical_line == "accruals_and_deferred_income"

        session.execute(
            text(
                """
                UPDATE account_mappings
                SET canonical_line = 'accruals'
                WHERE canonical_line = 'accruals_and_deferred_income'
                """
            )
        )
        session.commit()
        set_rls_org_id(session, org_id)
        session.expire_all()

        after = session.execute(
            select(AccountMapping).where(AccountMapping.id == row_id)
        ).scalar_one()
        assert after.canonical_line == "accruals"
        assert after.source_code == "2100"
        assert after.source_name == "Accruals"
        assert after.method == "manual"
        assert after.is_confirmed is True
