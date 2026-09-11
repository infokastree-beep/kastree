"""API: POST /trial-balances/convert-gl — review only, no TB created."""

from __future__ import annotations

from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from tests.conftest import auth_headers


def _clean_gl_csv() -> bytes:
    return (
        "Date,Account Code,Account Name,Debit,Credit\n"
        "2025-01-05,1000,Bank,10000.00,0\n"
        "2025-01-05,3000,Share Capital,0,10000.00\n"
        "2025-03-15,1100,Trade Receivables,2500.00,0\n"
        "2025-03-15,4000,Sales,0,2500.00\n"
    ).encode("utf-8")


def _broken_gl_csv() -> bytes:
    return (
        "Date,Account Code,Account Name,Debit,Credit\n"
        "2025-01-05,1000,Bank,10000.00,0\n"
        "2025-01-05,3000,Share Capital,0,10000.00\n"
        "2025-03-15,1100,Trade Receivables,2500.00,0\n"
    ).encode("utf-8")


@pytest.mark.asyncio
async def test_convert_gl_clean_returns_rows_without_creating_tb(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    org_id = provisioned_org["org_id"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        before = session.execute(
            text("SELECT COUNT(*) FROM trial_balances")
        ).scalar_one()

    resp = await api_client.post(
        "/trial-balances/convert-gl",
        headers=headers,
        files={"file": ("clean-gl.csv", BytesIO(_clean_gl_csv()), "text/csv")},
        data={
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
            "opening_balance_mode": "C",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "tb_id" not in body
    assert body["pipeline_eligible"] is True
    assert body["mode"] == "C"
    assert len(body["rows"]) >= 3
    assert body["total_debits"] == body["total_credits"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        after = session.execute(
            text("SELECT COUNT(*) FROM trial_balances")
        ).scalar_one()
    assert after == before


@pytest.mark.asyncio
async def test_convert_gl_unbalanced_rejected_clear_error(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    org_id = provisioned_org["org_id"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        before = session.execute(
            text("SELECT COUNT(*) FROM trial_balances")
        ).scalar_one()

    resp = await api_client.post(
        "/trial-balances/convert-gl",
        headers=headers,
        files={"file": ("broken-gl.csv", BytesIO(_broken_gl_csv()), "text/csv")},
        data={
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
            "opening_balance_mode": "C",
        },
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "GL_TB_UNBALANCED"
    assert "difference" in detail

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        after = session.execute(
            text("SELECT COUNT(*) FROM trial_balances")
        ).scalar_one()
    assert after == before


@pytest.mark.asyncio
async def test_convert_gl_mode_b_without_prior_rejected(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    resp = await api_client.post(
        "/trial-balances/convert-gl",
        headers=headers,
        files={"file": ("clean-gl.csv", BytesIO(_clean_gl_csv()), "text/csv")},
        data={
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
            "opening_balance_mode": "B",
        },
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "GL_MODE_B_REQUIRES_PRIOR"


@pytest.mark.asyncio
async def test_convert_gl_mixed_currency_symbols_rejected(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """GL path must raise the same AmbiguousCurrencyError gate as TB upload."""
    mixed = (
        "Date,Account Code,Account Name,Debit,Credit,Journal\n"
        "2025-06-01,1000,Bank,\"€10,000.00\",,J1\n"
        "2025-06-01,3000,Capital,,\"£10,000.00\",J1\n"
    ).encode("utf-8")
    headers = auth_headers(provisioned_org["token"])
    resp = await api_client.post(
        "/trial-balances/convert-gl",
        headers=headers,
        files={"file": ("mixed-symbol-gl.csv", BytesIO(mixed), "text/csv")},
        data={
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
            "opening_balance_mode": "C",
        },
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "AMBIGUOUS_CURRENCY"
    assert set(detail["symbols"]) == {"£", "€"}
    assert "Multiple currency symbols detected" in detail["detail"]
