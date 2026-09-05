"""Trial balance soft-delete + archived_records integration tests."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.archived_record import ArchivedRecord
from app.models.trial_balance import TrialBalance
from app.services.archival import RETENTION_YEARS, add_years, sha256_hex
from tests.conftest import auth_headers, balanced_tb_xlsx_bytes


async def _upload_tb(
    api_client: AsyncClient,
    *,
    headers: dict[str, str],
    company_id: str,
    period_end: str,
) -> str:
    files = {
        "file": (
            "tb.xlsx",
            balanced_tb_xlsx_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    upload = await api_client.post(
        "/trial-balances/upload",
        data={
            "company_id": str(company_id),
            "period_end": period_end,
            "currency": "GBP",
        },
        files=files,
        headers=headers,
    )
    assert upload.status_code == 202, upload.text
    return upload.json()["tb_id"]


@pytest.mark.asyncio
async def test_soft_delete_trial_balance_archives_and_hides_from_list(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    company_id = str(provisioned_org["company_id"])
    org_id = provisioned_org["org_id"]
    client_id = provisioned_org["client_id"]
    tb_id = await _upload_tb(
        api_client,
        headers=headers,
        company_id=company_id,
        period_end="2026-03-31",
    )
    tb_uuid = uuid.UUID(tb_id)

    deleted = await api_client.delete(f"/trial-balances/{tb_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    body = deleted.json()
    assert body["id"] == tb_id
    assert body["is_deleted"] is True
    assert body["deleted_at"] is not None

    listed = await api_client.get(
        f"/trial-balances?company_id={company_id}",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert all(item["id"] != tb_id for item in listed.json()["items"])

    status = await api_client.get(f"/trial-balances/{tb_id}/status", headers=headers)
    assert status.status_code == 404

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.get(TrialBalance, tb_uuid)
        assert row is not None
        assert row.is_deleted is True
        assert row.deleted_at is not None

        archive = session.scalar(
            select(ArchivedRecord).where(
                ArchivedRecord.entity_type == "trial_balance",
                ArchivedRecord.entity_id == tb_uuid,
                ArchivedRecord.archive_reason == "user_deleted",
            )
        )
        assert archive is not None
        assert archive.org_id == org_id
        assert archive.client_id == client_id
        assert archive.archived_data["id"] == tb_id
        assert archive.archived_data["period_end"] == "2026-03-31"
        assert archive.archived_data["is_deleted"] is True
        assert len(archive.archive_hash) == 64
        assert archive.archive_hash == sha256_hex(archive.archived_data)
        independent = hashlib.sha256(
            json.dumps(
                archive.archived_data,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        assert archive.archive_hash == independent
        today = date.today()
        expected = add_years(today, RETENTION_YEARS)
        assert abs((archive.retention_until - expected).days) <= 1


@pytest.mark.asyncio
async def test_soft_delete_frees_period_for_reupload(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    company_id = str(provisioned_org["company_id"])
    first_id = await _upload_tb(
        api_client,
        headers=headers,
        company_id=company_id,
        period_end="2026-04-30",
    )
    deleted = await api_client.delete(f"/trial-balances/{first_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    second_id = await _upload_tb(
        api_client,
        headers=headers,
        company_id=company_id,
        period_end="2026-04-30",
    )
    assert second_id != first_id

    listed = await api_client.get(
        f"/trial-balances?company_id={company_id}",
        headers=headers,
    )
    ids = {item["id"] for item in listed.json()["items"]}
    assert second_id in ids
    assert first_id not in ids


@pytest.mark.asyncio
async def test_soft_delete_rolls_back_when_archive_fails(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    company_id = str(provisioned_org["company_id"])
    org_id = provisioned_org["org_id"]
    tb_id = await _upload_tb(
        api_client,
        headers=headers,
        company_id=company_id,
        period_end="2026-05-31",
    )
    tb_uuid = uuid.UUID(tb_id)

    async def _boom(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("simulated archive write failure")

    monkeypatch.setattr(
        "app.routers.trial_balances.archive_trial_balance_user_deleted",
        _boom,
    )
    with pytest.raises(RuntimeError, match="simulated archive write failure"):
        await api_client.delete(f"/trial-balances/{tb_id}", headers=headers)

    listed = await api_client.get(
        f"/trial-balances?company_id={company_id}",
        headers=headers,
    )
    assert any(item["id"] == tb_id for item in listed.json()["items"])

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.get(TrialBalance, tb_uuid)
        assert row is not None
        assert row.is_deleted is False
        assert row.deleted_at is None
        archive = session.scalar(
            select(ArchivedRecord).where(
                ArchivedRecord.entity_id == tb_uuid,
                ArchivedRecord.entity_type == "trial_balance",
            )
        )
        assert archive is None
