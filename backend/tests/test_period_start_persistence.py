"""period_start is stored on the trial balance for both upload paths."""

from __future__ import annotations

from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from tests.conftest import auth_headers, balanced_tb_xlsx_bytes


def _gl_csv() -> bytes:
    return (
        "Date,Account Code,Account Name,Debit,Credit\n"
        "2025-04-05,1000,Bank,10000.00,0\n"
        "2025-04-05,3000,Share Capital,0,10000.00\n"
        "2025-06-15,1100,Trade Receivables,2500.00,0\n"
        "2025-06-15,4000,Sales,0,2500.00\n"
    ).encode("utf-8")


def _tb_row(org_id: object, tb_id: str) -> dict[str, object]:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = (
            session.execute(
                text(
                    "SELECT id::text, period_start::text, period_end::text, status "
                    "FROM trial_balances WHERE id = :tb_id"
                ),
                {"tb_id": tb_id},
            )
            .mappings()
            .one()
        )
    return dict(row)


@pytest.mark.asyncio
async def test_standard_upload_stores_period_start(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    upload = await api_client.post(
        "/trial-balances/upload",
        headers=headers,
        files={
            "file": (
                "tb.xlsx",
                balanced_tb_xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={
            "company_id": str(provisioned_org["company_id"]),
            "period_start": "2026-01-01",
            "period_end": "2026-09-30",
            "currency": "GBP",
        },
    )
    assert upload.status_code == 202, upload.text
    row = _tb_row(provisioned_org["org_id"], upload.json()["tb_id"])
    assert row["period_start"] == "2026-01-01"
    assert row["period_end"] == "2026-09-30"


@pytest.mark.asyncio
async def test_gl_conversion_period_start_is_stored_on_confirm_upload(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """convert-gl keeps the range for review. The confirm upload writes the column."""
    headers = auth_headers(provisioned_org["token"])
    org_id = provisioned_org["org_id"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        before = session.execute(
            text("SELECT COUNT(*) FROM trial_balances")
        ).scalar_one()

    converted = await api_client.post(
        "/trial-balances/convert-gl",
        headers=headers,
        files={"file": ("ledger.csv", BytesIO(_gl_csv()), "text/csv")},
        data={
            "period_start": "2025-04-01",
            "period_end": "2025-06-30",
            "opening_balance_mode": "C",
        },
    )
    assert converted.status_code == 200, converted.text
    body = converted.json()
    assert body["period_start"] == "2025-04-01"
    assert body["period_end"] == "2025-06-30"
    assert "tb_id" not in body

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        after_convert = session.execute(
            text("SELECT COUNT(*) FROM trial_balances")
        ).scalar_one()
    assert after_convert == before

    upload = await api_client.post(
        "/trial-balances/upload",
        headers=headers,
        files={
            "file": (
                "converted-trial-balance.xlsx",
                balanced_tb_xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={
            "company_id": str(provisioned_org["company_id"]),
            "period_start": body["period_start"],
            "period_end": body["period_end"],
            "currency": "GBP",
        },
    )
    assert upload.status_code == 202, upload.text
    row = _tb_row(org_id, upload.json()["tb_id"])
    assert row["id"] == upload.json()["tb_id"]
    assert row["period_start"] == "2025-04-01"
    assert row["period_end"] == "2025-06-30"


@pytest.mark.asyncio
async def test_upload_rejects_period_start_after_period_end(
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

    upload = await api_client.post(
        "/trial-balances/upload",
        headers=headers,
        files={
            "file": (
                "tb.xlsx",
                balanced_tb_xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={
            "company_id": str(provisioned_org["company_id"]),
            "period_start": "2026-12-31",
            "period_end": "2026-01-01",
            "currency": "GBP",
        },
    )
    assert upload.status_code == 400, upload.text
    assert upload.json()["detail"] == "Period start must be on or before period end."

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        after = session.execute(
            text("SELECT COUNT(*) FROM trial_balances")
        ).scalar_one()
    assert after == before
