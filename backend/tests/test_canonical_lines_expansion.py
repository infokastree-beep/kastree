"""Canonical lines expansion — six new lines + accruals rename migration."""

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
    compute_net_profit,
)
from app.services.validator import ASSET_LINES, EQUITY_LINES_SOFP, LIABILITY_LINES

NEW_CANONICAL_LINES: tuple[str, ...] = (
    "investments",
    "prepayments_and_accrued_income",
    "provisions",
    "taxation_and_social_security",
    "share_premium",
    "revaluation_reserve",
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


@pytest.mark.parametrize("line", NEW_CANONICAL_LINES)
def test_new_canonical_lines_in_llm_allowlist(line: str) -> None:
    assert line in MAPPING_TIE_BREAKER_CANONICAL_LINES


@pytest.mark.parametrize("line", NEW_CANONICAL_LINES)
def test_new_canonical_lines_not_in_profit_and_loss_lines(line: str) -> None:
    assert line not in PROFIT_AND_LOSS_LINES


def test_accruals_renamed_in_llm_allowlist() -> None:
    assert "accruals_and_deferred_income" in MAPPING_TIE_BREAKER_CANONICAL_LINES
    assert "accruals" not in MAPPING_TIE_BREAKER_CANONICAL_LINES


def test_sofp_display_order_includes_new_lines() -> None:
    assert SOFP_ASSET_ORDER == (
        "property_plant_equipment",
        "intangible_assets",
        "investments",
        "inventory",
        "trade_receivables",
        "prepayments_and_accrued_income",
        "cash",
    )
    assert SOFP_LIABILITY_ORDER == (
        "trade_payables",
        "provisions",
        "accruals_and_deferred_income",
        "taxation_and_social_security",
        "loans",
    )


def test_validator_line_sets_include_new_balance_sheet_lines() -> None:
    assert "investments" in ASSET_LINES
    assert "prepayments_and_accrued_income" in ASSET_LINES
    assert "provisions" in LIABILITY_LINES
    assert "taxation_and_social_security" in LIABILITY_LINES
    assert "accruals_and_deferred_income" in LIABILITY_LINES
    assert "share_premium" in EQUITY_LINES_SOFP
    assert "revaluation_reserve" in EQUITY_LINES_SOFP


@pytest.mark.parametrize("line", NEW_CANONICAL_LINES)
def test_mapper_parse_llm_mappings_accepts_new_canonical_lines(line: str) -> None:
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
        "mappings": [{"index": 1, "canonical_line": line, "reasoning": "Test mapping"}]
    }
    results = _parse_llm_mappings(unmapped, payload)
    assert results[0].canonical_line == line
    assert results[0].method == "llm"


def test_sofp_places_new_lines_in_expected_positions() -> None:
    re_id = uuid.uuid4()
    accounts = [
        _acct("1100", net_balance="1000.00", canonical_line="property_plant_equipment"),
        _acct("1200", net_balance="500.00", canonical_line="intangible_assets"),
        _acct("1250", net_balance="800.00", canonical_line="investments"),
        _acct("1300", net_balance="200.00", canonical_line="inventory"),
        _acct("1400", net_balance="300.00", canonical_line="trade_receivables"),
        _acct("1450", net_balance="150.00", canonical_line="prepayments_and_accrued_income"),
        _acct("1500", net_balance="250.00", canonical_line="cash"),
        _acct("2100", net_balance="-400.00", canonical_line="trade_payables"),
        _acct("2150", net_balance="-100.00", canonical_line="provisions"),
        _acct("2200", net_balance="-50.00", canonical_line="accruals_and_deferred_income"),
        _acct("2250", net_balance="-75.00", canonical_line="taxation_and_social_security"),
        _acct("2300", net_balance="-500.00", canonical_line="loans"),
        _acct("3000", net_balance="-1000.00", canonical_line="share_capital"),
        _acct("3050", net_balance="-200.00", canonical_line="share_premium"),
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
    assert codes.index("prepayments_and_accrued_income") > codes.index("trade_receivables")
    assert codes.index("provisions") > codes.index("trade_payables")
    assert codes.index("taxation_and_social_security") > codes.index(
        "accruals_and_deferred_income"
    )
    assert codes.index("share_premium") > codes.index("share_capital")
    assert codes.index("revaluation_reserve") > codes.index("retained_earnings")

    total_equity = next(line for line in lines if line.line_item_code == "total_equity")
    assert total_equity.amount == Decimal("1950.00")  # 1000 + 200 + 600 + 150


def test_compute_net_profit_unchanged_by_new_balance_sheet_lines() -> None:
    accounts = [
        _acct("4000", net_balance="-1000.00", canonical_line="revenue"),
        _acct("5000", net_balance="400.00", canonical_line="cost_of_sales"),
        _acct("1250", net_balance="800.00", canonical_line="investments"),
        _acct("3050", net_balance="-200.00", canonical_line="share_premium"),
    ]
    assert compute_net_profit(accounts) == Decimal("600.00")


def test_accruals_migration_renames_existing_rows_without_data_loss(
    provisioned_org: dict,
) -> None:
    """Data migration SQL: accruals -> accruals_and_deferred_income."""
    row_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        session.add(
            AccountMapping(
                id=row_id,
                company_id=provisioned_org["company_id"],
                source_code="2100",
                source_name="Accruals",
                canonical_line="accruals",
                method="manual",
                is_confirmed=True,
            )
        )
        session.commit()

        before = session.execute(
            select(AccountMapping).where(AccountMapping.id == row_id)
        ).scalar_one()
        assert before.canonical_line == "accruals"

        session.execute(
            text(
                """
                UPDATE account_mappings
                SET canonical_line = 'accruals_and_deferred_income'
                WHERE canonical_line = 'accruals'
                """
            )
        )
        session.commit()

        after = session.execute(
            select(AccountMapping).where(AccountMapping.id == row_id)
        ).scalar_one()
        assert after.canonical_line == "accruals_and_deferred_income"
        assert after.source_code == "2100"
        assert after.source_name == "Accruals"
        assert after.method == "manual"
        assert after.is_confirmed is True
