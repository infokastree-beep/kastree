"""API integration tests — happy path, cross-org 404, real-Postgres RLS signup."""

from __future__ import annotations

import time
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.trial_balance import TrialBalance
from app.services.org_provisioning import (
    organisation_id_for_clerk_org,
    provision_first_signup,
)
from tests.conftest import (
    auth_headers,
    balanced_tb_xlsx_bytes,
    make_access_token,
)


@pytest.mark.asyncio
async def test_clerk_webhook_provisions_first_org_under_rls(
    api_client: AsyncClient,
) -> None:
    """HTTP organization.created creates org+user under FORCE RLS (no BYPASSRLS)."""
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_wh_{suffix}"
    clerk_user_id = f"user_wh_{suffix}"
    payload = {
        "type": "organization.created",
        "data": {
            "id": clerk_org_id,
            "name": "Webhook Org",
            "created_by": clerk_user_id,
            "email": f"owner-{suffix}@example.com",
        },
    }
    response = await api_client.post("/auth/webhook", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "created"
    org_id = uuid.UUID(body["organisation_id"])
    assert org_id == organisation_id_for_clerk_org(clerk_org_id)

    # Visible under matching RLS; invisible under a different org setting.
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.execute(
            text("SELECT name FROM organisations WHERE id = :oid"),
            {"oid": str(org_id)},
        ).one()
        assert row[0] == "Webhook Org"
        users = session.execute(
            text("SELECT email FROM users WHERE org_id = :oid"),
            {"oid": str(org_id)},
        ).all()
        assert len(users) == 1

        other = uuid.uuid4()
        set_rls_org_id(session, other)
        hidden = session.execute(
            text("SELECT count(*) FROM organisations WHERE id = :oid"),
            {"oid": str(org_id)},
        ).scalar()
        assert hidden == 0

        # Cleanup
        set_rls_org_id(session, org_id)
        session.execute(text("DELETE FROM users WHERE org_id = :oid"), {"oid": str(org_id)})
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"), {"oid": str(org_id)}
        )
        session.commit()


def test_fresh_signup_succeeds_under_force_rls_without_bypass() -> None:
    """Real Postgres: INSERT org without SET LOCAL fails; bootstrap succeeds.

    Uses the findraft role (rolbypassrls=false) with FORCE ROW LEVEL SECURITY so
    table ownership does not silently skip policies. Confirms the chicken-and-egg
    fix — generate UUID, SET LOCAL, then INSERT org + user in one transaction.
    """
    with SyncSessionLocal() as session:
        bypass = session.execute(
            text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).scalar()
        assert bypass is False
        forced = session.execute(
            text(
                "SELECT relforcerowsecurity FROM pg_class "
                "WHERE relname = 'organisations'"
            )
        ).scalar()
        assert forced is True

    # Without SET LOCAL / set_config, INSERT must fail under FORCE RLS.
    naked_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        with pytest.raises(DBAPIError):
            session.execute(
                text(
                    "INSERT INTO organisations (id, clerk_org_id, name) "
                    "VALUES (:id, :clerk, :name)"
                ),
                {
                    "id": str(naked_id),
                    "clerk": f"clerk_naked_{naked_id.hex[:8]}",
                    "name": "Should Fail",
                },
            )
            session.commit()
        session.rollback()

    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_rls_{suffix}"
    clerk_user_id = f"user_rls_{suffix}"
    with SyncSessionLocal() as session:
        provisioned = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name="RLS Bootstrap Org",
            clerk_user_id=clerk_user_id,
            email=f"rls-{suffix}@example.com",
            role="owner",
        )
        org_id = provisioned.organisation.id
        user_id = provisioned.user.id
        assert org_id == organisation_id_for_clerk_org(clerk_org_id)
        assert provisioned.created is True
        session.commit()

    assert user_id is not None

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        assert (
            session.execute(
                text("SELECT count(*) FROM organisations WHERE id = :oid"),
                {"oid": str(org_id)},
            ).scalar()
            == 1
        )
        assert (
            session.execute(
                text("SELECT count(*) FROM users WHERE org_id = :oid"),
                {"oid": str(org_id)},
            ).scalar()
            == 1
        )
        set_rls_org_id(session, uuid.uuid4())
        assert (
            session.execute(
                text("SELECT count(*) FROM organisations WHERE id = :oid"),
                {"oid": str(org_id)},
            ).scalar()
            == 0
        )
        set_rls_org_id(session, org_id)
        session.execute(text("DELETE FROM users WHERE org_id = :oid"), {"oid": str(org_id)})
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"), {"oid": str(org_id)}
        )
        session.commit()


# Covers existing_org-is-not-None idempotency only — not the IntegrityError race branch
# (true concurrent delivery needs thread/process concurrency against the same DB; accepted gap).
def test_duplicate_provision_first_signup_returns_exists_not_raise() -> None:
    """Serialised duplicate organization.created: second call returns created=False.

    Models the ordering where the first delivery has already inserted (and
    committed) before the second runs — without raising an unhandled 500.
    """
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_dup_{suffix}"
    clerk_user_id = f"user_dup_{suffix}"
    email = f"dup-{suffix}@example.com"

    with SyncSessionLocal() as session:
        first = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name="Dup Org",
            clerk_user_id=clerk_user_id,
            email=email,
            role="owner",
        )
        org_id = first.organisation.id
        user_id = first.user.id
        assert first.created is True
        session.commit()

    with SyncSessionLocal() as session:
        second = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name="Dup Org Retried",
            clerk_user_id=clerk_user_id,
            email=email,
            role="owner",
        )
        session.commit()
        assert second.created is False
        assert second.organisation.id == org_id
        assert second.user.id == user_id

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        assert (
            session.execute(
                text("SELECT count(*) FROM organisations WHERE id = :oid"),
                {"oid": str(org_id)},
            ).scalar()
            == 1
        )
        assert (
            session.execute(
                text("SELECT count(*) FROM users WHERE org_id = :oid"),
                {"oid": str(org_id)},
            ).scalar()
            == 1
        )
        session.execute(text("DELETE FROM users WHERE org_id = :oid"), {"oid": str(org_id)})
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"), {"oid": str(org_id)}
        )
        session.commit()


@pytest.mark.asyncio
async def test_full_happy_path_upload_to_statements(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    files = {
        "file": (
            "tb.xlsx",
            balanced_tb_xlsx_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    form = {
        "company_id": str(provisioned_org["company_id"]),
        "period_end": "2026-07-31",
        "currency": "GBP",
    }
    upload = await api_client.post(
        "/trial-balances/upload",
        data=form,
        files=files,
        headers=headers,
    )
    assert upload.status_code == 202, upload.text
    body = upload.json()
    assert body["status"] == "pending"
    assert "tb_id" in body and "job_id" in body
    tb_id = body["tb_id"]

    # Poll until parse+map complete (BackgroundTasks).
    status_body = None
    for _ in range(40):
        status_resp = await api_client.get(
            f"/trial-balances/{tb_id}/status", headers=headers
        )
        assert status_resp.status_code == 200
        status_body = status_resp.json()
        assert status_body["tb_id"] == tb_id
        jobs = {job["job_type"]: job["status"] for job in status_body["jobs"]}
        if jobs.get("parse") == "complete" and jobs.get("map") == "complete":
            break
        if status_body["status"] == "failed":
            pytest.fail(f"processing failed: {status_body}")
        time.sleep(0.05)
    else:
        pytest.fail(f"timed out waiting for parse/map: {status_body}")

    mapping_resp = await api_client.get(
        f"/trial-balances/{tb_id}/mapping", headers=headers
    )
    assert mapping_resp.status_code == 200, mapping_resp.text
    mapping_body = mapping_resp.json()
    assert mapping_body["tb_id"] == tb_id
    assert "mapping_rate" in mapping_body
    assert isinstance(mapping_body["mappings"], list)
    assert len(mapping_body["mappings"]) >= 1

    # Confirm with explicit canonical lines (BS lines are outside unambiguous ranges).
    confirm_items = []
    for item in mapping_body["mappings"]:
        code = item["source_code"]
        if code == "1100":
            canonical = "cash"
        elif code == "4100":
            canonical = "revenue"
        elif code == "6100":
            canonical = "operating_expenses"
        elif code == "3000":
            canonical = "share_capital"
        elif code == "3100":
            canonical = "retained_earnings"
        else:
            canonical = item["suggested_canonical_line"]
        confirm_items.append(
            {
                "id": item["id"],
                "canonical_line": canonical,
                "is_confirmed": True,
                "is_ignored": False,
            }
        )
    confirm = await api_client.post(
        f"/trial-balances/{tb_id}/mapping/confirm",
        json={"mappings": confirm_items},
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "validating"

    validation_body = None
    for _ in range(40):
        validation = await api_client.get(
            f"/trial-balances/{tb_id}/validation", headers=headers
        )
        if validation.status_code == 200:
            validation_body = validation.json()
            break
        time.sleep(0.05)
    else:
        pytest.fail("timed out waiting for validation results")

    assert validation_body["tb_id"] == tb_id
    assert "all_passed" in validation_body
    assert "can_generate_statements" in validation_body
    assert isinstance(validation_body["checks"], list)
    assert validation_body["can_generate_statements"] is True

    gen = await api_client.post(
        f"/trial-balances/{tb_id}/statements", headers=headers
    )
    assert gen.status_code == 200, gen.text
    assert len(gen.json()["statements"]) == 3

    got = await api_client.get(
        f"/trial-balances/{tb_id}/statements", headers=headers
    )
    assert got.status_code == 200, got.text
    statements = got.json()["statements"]
    assert len(statements) == 3
    types = {block["statement_type"] for block in statements}
    assert types == {"SOPL", "SOFP", "SOCIE"}


@pytest.mark.asyncio
async def test_cross_org_trial_balance_returns_404_not_403(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers_a = auth_headers(provisioned_org["token"])
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
            "company_id": str(provisioned_org["company_id"]),
            "period_end": "2026-06-30",
            "currency": "GBP",
        },
        files=files,
        headers=headers_a,
    )
    assert upload.status_code == 202, upload.text
    tb_id = upload.json()["tb_id"]

    # Second org
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_b_{suffix}"
    clerk_user_id = f"user_b_{suffix}"
    with SyncSessionLocal() as session:
        other = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name="Other Org",
            clerk_user_id=clerk_user_id,
            email=f"other-{suffix}@example.com",
        )
        session.commit()
        other_org_id = other.organisation.id

    token_b = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        org_uuid=other_org_id,
    )
    headers_b = auth_headers(token_b)

    for path in (
        f"/trial-balances/{tb_id}/status",
        f"/trial-balances/{tb_id}/mapping",
        f"/trial-balances/{tb_id}/validation",
        f"/trial-balances/{tb_id}/statements",
    ):
        response = await api_client.get(path, headers=headers_b)
        assert response.status_code == 404, f"{path} => {response.status_code}"
        assert response.status_code != 403

    with SyncSessionLocal() as session:
        set_rls_org_id(session, other_org_id)
        session.execute(
            text("DELETE FROM users WHERE org_id = :oid"), {"oid": str(other_org_id)}
        )
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"),
            {"oid": str(other_org_id)},
        )
        session.commit()


@pytest.mark.asyncio
async def test_list_trial_balances_for_client(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    company_id = provisioned_org["company_id"]
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
            "period_end": "2026-07-31",
            "currency": "GBP",
        },
        files=files,
        headers=headers,
    )
    assert upload.status_code == 202, upload.text
    tb_id = upload.json()["tb_id"]

    listed = await api_client.get(
        f"/trial-balances?company_id={company_id}",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] >= 1
    assert any(item["id"] == tb_id for item in body["items"])
    row = next(item for item in body["items"] if item["id"] == tb_id)
    assert row["period_end"] == "2026-07-31"
    assert row["status"] in {
        "pending",
        "parsing",
        "mapping",
        "validating",
        "generating",
        "analysing",
        "complete",
        "failed",
    }
    assert "created_at" in row


@pytest.mark.asyncio
async def test_list_trial_balances_cross_org_client_404(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_other_{suffix}"
    clerk_user_id = f"user_other_{suffix}"
    with SyncSessionLocal() as session:
        other = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name="Other Org",
            clerk_user_id=clerk_user_id,
            email=f"other-{suffix}@example.com",
        )
        session.commit()
        other_org_id = other.organisation.id

    token_b = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        org_uuid=other_org_id,
    )
    response = await api_client.get(
        f"/trial-balances?company_id={provisioned_org['company_id']}",
        headers=auth_headers(token_b),
    )
    assert response.status_code == 404

    with SyncSessionLocal() as session:
        set_rls_org_id(session, other_org_id)
        session.execute(
            text("DELETE FROM users WHERE org_id = :oid"), {"oid": str(other_org_id)}
        )
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"),
            {"oid": str(other_org_id)},
        )
        session.commit()


@pytest.mark.asyncio
async def test_upload_stores_company_functional_currency_ignoring_form_value(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """trial_balances.currency must follow company.functional_currency, not the form field."""
    headers = auth_headers(provisioned_org["token"])
    client_id = provisioned_org["client_id"]
    created = await api_client.post(
        f"/clients/{client_id}/companies",
        headers=headers,
        json={"name": "EUR Upload Co", "functional_currency": "EUR"},
    )
    assert created.status_code == 201, created.text
    company_id = created.json()["id"]

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
            "company_id": company_id,
            "period_end": "2026-08-31",
            "currency": "GBP",
        },
        files=files,
        headers=headers,
    )
    assert upload.status_code == 202, upload.text
    tb_id = upload.json()["tb_id"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        row = session.execute(
            text("SELECT currency FROM trial_balances WHERE id = :id"),
            {"id": tb_id},
        ).one()
        assert row.currency == "EUR"


@pytest.mark.asyncio
async def test_get_statements_returns_company_functional_currency(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    client_id = provisioned_org["client_id"]
    created = await api_client.post(
        f"/clients/{client_id}/companies",
        headers=headers,
        json={"name": "EUR Statements Co", "functional_currency": "EUR"},
    )
    assert created.status_code == 201, created.text
    company_id = created.json()["id"]

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
            "company_id": company_id,
            "period_end": "2026-09-30",
            "currency": "EUR",
        },
        files=files,
        headers=headers,
    )
    assert upload.status_code == 202, upload.text
    tb_id = upload.json()["tb_id"]

    for _ in range(40):
        status_resp = await api_client.get(
            f"/trial-balances/{tb_id}/status", headers=headers
        )
        jobs = {job["job_type"]: job["status"] for job in status_resp.json()["jobs"]}
        if jobs.get("parse") == "complete" and jobs.get("map") == "complete":
            break
        time.sleep(0.05)
    else:
        pytest.fail("timed out waiting for parse/map")

    confirm = await api_client.post(
        f"/trial-balances/{tb_id}/mapping/confirm",
        headers=headers,
        json={"mappings": None},
    )
    assert confirm.status_code == 200, confirm.text

    for _ in range(40):
        validation = await api_client.get(
            f"/trial-balances/{tb_id}/validation", headers=headers
        )
        if validation.status_code == 200:
            break
        time.sleep(0.05)
    else:
        pytest.fail("timed out waiting for validation")

    gen = await api_client.post(
        f"/trial-balances/{tb_id}/statements", headers=headers
    )
    assert gen.status_code == 200, gen.text
    assert gen.json()["functional_currency"] == "EUR"

    got = await api_client.get(
        f"/trial-balances/{tb_id}/statements", headers=headers
    )
    assert got.status_code == 200, got.text
    assert got.json()["functional_currency"] == "EUR"


@pytest.mark.asyncio
async def test_failed_upload_can_be_retried_same_company_period(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """A failed TB must not permanently occupy UNIQUE(company_id, period_end)."""
    headers = auth_headers(provisioned_org["token"])
    company_id = str(provisioned_org["company_id"])
    period_end = "2026-01-31"

    # Seed a failed row the same way a bad parse would leave it.
    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        failed = TrialBalance(
            company_id=provisioned_org["company_id"],
            period_end=date(2026, 1, 31),
            file_url="file:///tmp/findraft-uploads/broken.xlsx",
            file_type="xlsx",
            file_size_bytes=16,
            status="failed",
            currency="GBP",
            error_message="File is not a zip file",
        )
        session.add(failed)
        session.flush()
        failed_id = failed.id
        session.commit()

    # Re-upload a valid file for the same company + period → 202, same tb id reused.
    files = {
        "file": (
            "tb.xlsx",
            balanced_tb_xlsx_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    retry = await api_client.post(
        "/trial-balances/upload",
        data={
            "company_id": company_id,
            "period_end": period_end,
            "currency": "GBP",
        },
        files=files,
        headers=headers,
    )
    assert retry.status_code == 202, retry.text
    body = retry.json()
    assert body["tb_id"] == str(failed_id)
    assert body["status"] == "pending"

    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        row = session.get(TrialBalance, failed_id)
        assert row is not None
        # BackgroundTasks may already have advanced pending → parsing/mapping.
        assert row.status != "failed"
        assert row.error_message is None
        assert row.period_end == date(2026, 1, 31)


@pytest.mark.asyncio
async def test_duplicate_non_failed_upload_returns_409_with_existing_tb_id(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    company_id = str(provisioned_org["company_id"])
    period_end = "2026-02-28"
    files = {
        "file": (
            "tb.xlsx",
            balanced_tb_xlsx_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    first = await api_client.post(
        "/trial-balances/upload",
        data={
            "company_id": company_id,
            "period_end": period_end,
            "currency": "GBP",
        },
        files=files,
        headers=headers,
    )
    assert first.status_code == 202, first.text
    tb_id = first.json()["tb_id"]

    second = await api_client.post(
        "/trial-balances/upload",
        data={
            "company_id": company_id,
            "period_end": period_end,
            "currency": "GBP",
        },
        files=files,
        headers=headers,
    )
    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["existing_tb_id"] == tb_id
    assert "already exists" in detail["message"].lower()
    assert detail["existing_status"] in {
        "pending",
        "parsing",
        "mapping",
        "validating",
        "generating",
        "analysing",
        "complete",
        "failed",
    }
