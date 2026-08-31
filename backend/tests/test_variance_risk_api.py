"""Variance + risk API tests — generation, auto-detect, edge cases, JSONB round-trip."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.account_mapping import AccountMapping
from app.models.financial_statement import FinancialStatement
from app.models.statement_line_item import StatementLineItem
from app.models.trial_balance import TrialBalance
from app.models.variance_analysis import VarianceAnalysis
from app.schemas.variance import (
    MISSING_PRIOR_PERIOD_MESSAGE,
    PRIOR_STATEMENTS_MISSING_MESSAGE,
    VarianceAnalysisResult,
)
from tests.conftest import auth_headers


def _seed_tb(
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    period_end: date,
    lines: list[tuple[str, str, str, bool]],
    parsed_rows: list[dict] | None = None,
) -> uuid.UUID:
    """Insert a TB + SOPL statement lines under RLS. Returns tb_id.

    lines: (line_item_code, line_item_name, amount, is_subtotal)
    """
    tb_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        tb = TrialBalance(
            id=tb_id,
            company_id=company_id,
            period_end=period_end,
            file_url=f"/tmp/{tb_id}.xlsx",
            file_type="xlsx",
            status="complete",
            currency="GBP",
            parsed_data={"rows": parsed_rows or []},
        )
        session.add(tb)
        session.flush()
        fs = FinancialStatement(
            tb_id=tb.id,
            statement_type="SOPL",
            data={"lines": []},
        )
        session.add(fs)
        session.flush()
        for order, (code, name, amount, is_subtotal) in enumerate(lines):
            session.add(
                StatementLineItem(
                    statement_id=fs.id,
                    line_item_code=code,
                    line_item_name=name,
                    amount=Decimal(amount),
                    is_subtotal=is_subtotal,
                    display_order=order,
                )
            )
        # Empty SOFP so variance loader finds SOPL+SOFP statements.
        sofp = FinancialStatement(
            tb_id=tb.id,
            statement_type="SOFP",
            data={"lines": []},
        )
        session.add(sofp)
        session.flush()
        session.add(
            StatementLineItem(
                statement_id=sofp.id,
                line_item_code="cash",
                line_item_name="Cash",
                amount=Decimal("1000.00"),
                is_subtotal=False,
                display_order=0,
            )
        )
        session.commit()
    return tb_id


def _seed_tb_without_statements(
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    period_end: date,
    parsed_rows: list[dict] | None = None,
) -> uuid.UUID:
    """TB that is uploaded/mapped-ready but never had POST .../statements called."""
    tb_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            TrialBalance(
                id=tb_id,
                company_id=company_id,
                period_end=period_end,
                file_url=f"/tmp/{tb_id}.xlsx",
                file_type="xlsx",
                status="mapping",
                currency="GBP",
                parsed_data={"rows": parsed_rows or []},
            )
        )
        session.commit()
    return tb_id


def _seed_mapping(
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    source_code: str,
    source_name: str,
    canonical_line: str,
) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            AccountMapping(
                company_id=company_id,
                source_code=source_code,
                source_name=source_name,
                canonical_line=canonical_line,
                confidence=Decimal("1.00"),
                method="manual",
                is_confirmed=True,
            )
        )
        session.commit()


@pytest.mark.asyncio
async def test_variance_generation_with_real_prior_period(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    headers = auth_headers(provisioned_org["token"])

    prior_id = _seed_tb(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 6, 30),
        lines=[
            ("revenue", "Revenue", "210000.00", False),
            ("gross_profit", "Gross profit", "210000.00", True),
        ],
    )
    current_id = _seed_tb(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 7, 31),
        lines=[
            ("revenue", "Revenue", "250000.00", False),
            ("gross_profit", "Gross profit", "250000.00", True),
        ],
    )

    response = await api_client.post(
        f"/trial-balances/{current_id}/variance",
        headers=headers,
        json={"prior_tb_id": str(prior_id)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["variance_available"] is True
    assert body["tb_id"] == str(current_id)
    assert body["prior_tb_id"] == str(prior_id)
    assert body["materiality_threshold_pct"] == 10.0
    assert body["materiality_threshold_abs"] == "1000.00"

    revenue = next(item for item in body["items"] if item["line_item_code"] == "revenue")
    assert revenue["current_amount"] == "250000.00"
    assert revenue["prior_amount"] == "210000.00"
    assert revenue["variance_amount"] == "40000.00"
    assert revenue["variance_pct"] == "19.05"
    assert revenue["direction"] == "increase"
    assert revenue["is_material"] is True
    # Subtotals excluded from variance items.
    assert all(item["line_item_code"] != "gross_profit" for item in body["items"])

    got = await api_client.get(
        f"/trial-balances/{current_id}/variance", headers=headers
    )
    assert got.status_code == 200, got.text
    assert got.json()["prior_tb_id"] == str(prior_id)
    assert got.json()["items"] == body["items"]


@pytest.mark.asyncio
async def test_variance_auto_detect_picks_most_recent_prior_not_oldest(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """§6.2: most recent period_end < current — not an older TB by accident."""
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    headers = auth_headers(provisioned_org["token"])

    oldest_id = _seed_tb(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 1, 31),
        lines=[("revenue", "Revenue", "100000.00", False)],
    )
    expected_prior_id = _seed_tb(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 2, 28),
        lines=[("revenue", "Revenue", "200000.00", False)],
    )
    current_id = _seed_tb(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 3, 31),
        lines=[("revenue", "Revenue", "300000.00", False)],
    )

    response = await api_client.post(
        f"/trial-balances/{current_id}/variance",
        headers=headers,
        json={},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["variance_available"] is True
    assert body["prior_tb_id"] == str(expected_prior_id)
    assert body["prior_tb_id"] != str(oldest_id)

    revenue = next(item for item in body["items"] if item["line_item_code"] == "revenue")
    # Prior must be Feb (200k), not Jan (100k).
    assert revenue["prior_amount"] == "200000.00"
    assert revenue["current_amount"] == "300000.00"


@pytest.mark.asyncio
async def test_variance_no_prior_period_returns_unavailable_not_error(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    headers = auth_headers(provisioned_org["token"])

    current_id = _seed_tb(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 7, 31),
        lines=[("revenue", "Revenue", "250000.00", False)],
    )

    response = await api_client.post(
        f"/trial-balances/{current_id}/variance",
        headers=headers,
        json={},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["variance_available"] is False
    assert body["prior_tb_id"] is None
    assert body["message"] == MISSING_PRIOR_PERIOD_MESSAGE
    assert body["items"] == []


@pytest.mark.asyncio
async def test_variance_prior_without_statements_returns_unavailable_not_error(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """Prior uploaded/mapped but never POST .../statements — unavailable, not 4xx/wrong numbers."""
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    headers = auth_headers(provisioned_org["token"])

    prior_id = _seed_tb_without_statements(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 6, 30),
        parsed_rows=[
            {
                "account_code": "4100",
                "account_name": "Sales",
                "debit": "0.00",
                "credit": "210000.00",
                "net_balance": "-210000.00",
                "currency": "GBP",
                "row_index": 1,
            }
        ],
    )
    _seed_mapping(
        org_id=org_id,
        company_id=company_id,
        source_code="4100",
        source_name="Sales",
        canonical_line="revenue",
    )
    current_id = _seed_tb(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 7, 31),
        lines=[("revenue", "Revenue", "250000.00", False)],
    )

    response = await api_client.post(
        f"/trial-balances/{current_id}/variance",
        headers=headers,
        json={"prior_tb_id": str(prior_id)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["variance_available"] is False
    assert body["message"] == PRIOR_STATEMENTS_MISSING_MESSAGE
    assert body["items"] == []
    assert body["prior_tb_id"] == str(prior_id)
    # Must not invent variance amounts from the prior's raw mappings.
    assert "current_amount" not in body
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        stored = session.execute(
            select(VarianceAnalysis).where(VarianceAnalysis.tb_id == current_id)
        ).scalar_one_or_none()
        assert stored is None


@pytest.mark.asyncio
async def test_variance_items_jsonb_round_trips_to_same_pydantic_model(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """Write via to_jsonb(); read back into VarianceAnalysisResult — exact match."""
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    headers = auth_headers(provisioned_org["token"])

    prior_id = _seed_tb(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 5, 31),
        lines=[("revenue", "Revenue", "100.00", False)],
    )
    current_id = _seed_tb(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 6, 30),
        lines=[("revenue", "Revenue", "150.00", False)],
    )

    response = await api_client.post(
        f"/trial-balances/{current_id}/variance",
        headers=headers,
        json={"prior_tb_id": str(prior_id)},
    )
    assert response.status_code == 200, response.text

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.execute(
            select(VarianceAnalysis).where(VarianceAnalysis.tb_id == current_id)
        ).scalar_one()
        stored_jsonb = row.items
        round_tripped = VarianceAnalysisResult.model_validate(stored_jsonb)
        # Re-serialize must equal what was stored (to_jsonb round-trip).
        assert round_tripped.to_jsonb() == stored_jsonb
        # API items (minus commentary) must match the stored model.
        api_items = [
            {
                "line_item_code": item["line_item_code"],
                "line_item_name": item["line_item_name"],
                "current_amount": item["current_amount"],
                "prior_amount": item["prior_amount"],
                "variance_amount": item["variance_amount"],
                "variance_pct": item.get("variance_pct"),
                "direction": item["direction"],
                "is_material": item["is_material"],
            }
            for item in response.json()["items"]
        ]
        model_items = [
            item.model_dump(mode="json", exclude_none=False)
            for item in round_tripped.items
        ]
        assert model_items == api_items


@pytest.mark.asyncio
async def test_risk_negative_cash_flagged(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    headers = auth_headers(provisioned_org["token"])

    parsed_rows = [
        {
            "account_code": "1100",
            "account_name": "Cash at bank",
            "debit": "0.00",
            "credit": "500.00",
            "net_balance": "-500.00",
            "currency": "GBP",
            "row_index": 1,
        },
        {
            "account_code": "3000",
            "account_name": "Share capital",
            "debit": "0.00",
            "credit": "500.00",
            "net_balance": "-500.00",
            "currency": "GBP",
            "row_index": 2,
        },
    ]
    tb_id = _seed_tb(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 8, 31),
        lines=[("revenue", "Revenue", "0.00", False)],
        parsed_rows=parsed_rows,
    )
    _seed_mapping(
        org_id=org_id,
        company_id=company_id,
        source_code="1100",
        source_name="Cash at bank",
        canonical_line="cash",
    )
    _seed_mapping(
        org_id=org_id,
        company_id=company_id,
        source_code="3000",
        source_name="Share capital",
        canonical_line="share_capital",
    )

    response = await api_client.post(
        f"/trial-balances/{tb_id}/risk",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tb_id"] == str(tb_id)
    assert body["unusual_variance_history_months"] == 0
    rules = {flag["rule_name"] for flag in body["flags"]}
    assert "negative_cash" in rules
    cash_flag = next(flag for flag in body["flags"] if flag["rule_name"] == "negative_cash")
    assert cash_flag["severity"] == "warning"
    assert cash_flag["affected_accounts"] is not None
    assert cash_flag["affected_accounts"][0]["account_code"] == "1100"
    assert cash_flag["affected_accounts"][0]["net_balance"] == "-500.00"

    got = await api_client.get(f"/trial-balances/{tb_id}/risk", headers=headers)
    assert got.status_code == 200, got.text
    assert got.json()["flags"][0]["rule_name"] == "negative_cash"


@pytest.mark.asyncio
async def test_risk_rule2_skipped_with_empty_history_not_fabricated(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """Large variance_pct must NOT produce unusual_variance when history is empty."""
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    headers = auth_headers(provisioned_org["token"])

    prior_id = _seed_tb(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 4, 30),
        lines=[("revenue", "Revenue", "100.00", False)],
    )
    current_id = _seed_tb(
        org_id=org_id,
        company_id=company_id,
        period_end=date(2026, 5, 31),
        lines=[("revenue", "Revenue", "500.00", False)],
        parsed_rows=[
            {
                "account_code": "4100",
                "account_name": "Sales",
                "debit": "0.00",
                "credit": "500.00",
                "net_balance": "-500.00",
                "currency": "GBP",
                "row_index": 1,
            }
        ],
    )
    _seed_mapping(
        org_id=org_id,
        company_id=company_id,
        source_code="4100",
        source_name="Sales",
        canonical_line="revenue",
    )

    variance = await api_client.post(
        f"/trial-balances/{current_id}/variance",
        headers=headers,
        json={"prior_tb_id": str(prior_id)},
    )
    assert variance.status_code == 200, variance.text
    revenue = next(
        item for item in variance.json()["items"] if item["line_item_code"] == "revenue"
    )
    # 400% swing — would flag under the 3–11 month >50% tier if history existed.
    assert Decimal(revenue["variance_pct"]) > Decimal("50")

    risk = await api_client.post(
        f"/trial-balances/{current_id}/risk",
        headers=headers,
    )
    assert risk.status_code == 200, risk.text
    body = risk.json()
    assert body["unusual_variance_history_months"] == 0
    rule_names = {flag["rule_name"] for flag in body["flags"]}
    assert "unusual_variance" not in rule_names
