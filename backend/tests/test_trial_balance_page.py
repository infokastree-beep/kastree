"""Read-only Inputs > Trial balance page. The stored upload name is shown."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.trial_balance import TrialBalance
from app.services.org_provisioning import provision_first_signup
from tests.conftest import (
    _grant_append_only_delete,
    _revoke_append_only_delete,
    auth_headers,
    balanced_tb_xlsx_bytes,
    make_access_token,
)
from tests.test_adopted_trial_balance import _CASH_PAIR, _insert_tb
from tests.test_organisations_api import _add_org_user
from tests.test_role_enforcement import _set_role
from tests.test_tb_ingestion import _year_end

_PAGE_KEYS = {
    "trial_balance_id",
    "period_start",
    "period_end",
    "uploaded_at",
    "account_count",
    "currency",
    "file_name",
}


def _stored_uploaded_at(org_id: uuid.UUID, tb_id: uuid.UUID) -> datetime:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        stored = session.get(TrialBalance, tb_id)
        assert stored is not None
        return stored.created_at


@pytest.mark.asyncio
async def test_trial_balance_page_reads_the_adopted_file(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    clerk_org_id = provisioned_org["clerk_org_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(company_id, uuid.UUID)
    assert isinstance(clerk_org_id, str)
    headers = auth_headers(provisioned_org["token"])
    empty = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance",
        headers=headers,
    )
    assert empty.status_code == 200, empty.text
    assert set(empty.json()) == _PAGE_KEYS
    assert empty.json() == {
        "trial_balance_id": None,
        "period_start": None,
        "period_end": None,
        "uploaded_at": None,
        "account_count": None,
        "currency": None,
        "file_name": None,
    }

    tb_id = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=_CASH_PAIR,
        period_start=date(2026, 1, 1),
    )
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        stored_tb = session.get(TrialBalance, tb_id)
        assert stored_tb is not None
        stored_tb.original_filename = "year-end.xlsx"
        session.commit()
    adopted = await api_client.post(
        f"/year-ends/{year_end_id}/adopt-trial-balance",
        headers=headers,
        json={"trial_balance_id": str(tb_id)},
    )
    assert adopted.status_code == 200, adopted.text
    listed = await api_client.get(
        f"/year-ends/{year_end_id}/adoptable-trial-balances",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    page = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance",
        headers=headers,
    )
    assert page.status_code == 200, page.text
    body = page.json()
    assert set(body) == _PAGE_KEYS
    assert body["trial_balance_id"] == str(tb_id)
    assert body["period_start"] == "2026-01-01"
    assert body["period_end"] == "2026-12-31"
    assert body["account_count"] == listed.json()["items"][0]["account_count"]
    assert body["account_count"] == 2
    assert body["currency"] == "EUR"
    assert body["file_name"] == "year-end.xlsx"
    assert listed.json()["items"][0]["file_name"] == "year-end.xlsx"
    uploaded = datetime.fromisoformat(str(body["uploaded_at"]).replace("Z", "+00:00"))
    assert uploaded == _stored_uploaded_at(org_id, tb_id)
    for amount_key in ("debit", "credit", "amount", "net_balance"):
        assert amount_key not in body

    refused = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance",
        headers=headers,
        json={},
    )
    assert refused.status_code == 405, refused.text

    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=org_id,
        clerk_org_id=clerk_org_id,
        role="member",
        email_prefix="tb-page",
    )
    viewer_token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        role="owner",
        org_uuid=org_id,
    )
    _set_role(org_id=org_id, user_id=user_id, role="viewer")
    viewer = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance",
        headers=auth_headers(viewer_token),
    )
    assert viewer.status_code == 200, viewer.text
    assert viewer.json()["trial_balance_id"] == str(tb_id)


@pytest.mark.asyncio
async def test_trial_balance_page_is_hidden_from_another_organisation(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_tb_page_{suffix}"
    clerk_user_id = f"user_tb_page_{suffix}"
    with SyncSessionLocal() as session:
        other = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name="Other practice",
            clerk_user_id=clerk_user_id,
            email=f"tb-page-{suffix}@example.com",
        )
        session.commit()
        other_org_id = other.organisation.id
    token_b = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        org_uuid=other_org_id,
    )
    hidden = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance",
        headers=auth_headers(token_b),
    )
    assert hidden.status_code == 404, hidden.text
    assert hidden.json()["detail"] == "Year end not found"
    with SyncSessionLocal() as session:
        set_rls_org_id(session, other_org_id)
        granted = _grant_append_only_delete(session)
        session.execute(
            text("DELETE FROM users WHERE org_id = :oid"),
            {"oid": str(other_org_id)},
        )
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"),
            {"oid": str(other_org_id)},
        )
        _revoke_append_only_delete(session, granted)
        session.commit()


@pytest.mark.asyncio
async def test_upload_stores_the_safe_file_name(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    headers = auth_headers(provisioned_org["token"])
    upload = await api_client.post(
        "/trial-balances/upload",
        data={
            "company_id": str(provisioned_org["company_id"]),
            "period_end": "2026-08-31",
            "currency": "EUR",
        },
        files={
            "file": (
                "../../secret/accounts.xlsx",
                balanced_tb_xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=headers,
    )
    assert upload.status_code == 202, upload.text
    tb_id = uuid.UUID(str(upload.json()["tb_id"]))
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        stored = session.get(TrialBalance, tb_id)
        assert stored is not None
        assert stored.original_filename == "accounts.xlsx"
        assert "secret" not in (stored.file_url or "")
