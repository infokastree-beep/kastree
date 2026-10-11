"""Product 2 in production follows the practice acknowledgement or platform admin."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.config import settings
from app.db import AsyncSessionLocal, SyncSessionLocal, aset_rls_org_id, set_rls_org_id
from app.main import app
from app.models.organisation import Organisation
from app.models.user import User
from app.services.audit import append_audit_log
from app.services.beta import BETA_STATEMENT
from app.services.org_provisioning import provision_first_signup
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from tests.conftest import auth_headers, make_access_token, open_owner_session
from tests.test_organisations_api import _add_org_user

_FORBIDDEN = "You don't have permission to access this resource."
_ACCEPTED = {"accepted": True}

_CSV = (
    "Account Code,Account Name,Debit,Credit\n"
    "1000,Cash,10.00,0.00\n"
    "4000,Sales,0.00,10.00\n"
)


def _year_end_body(provisioned_org: dict) -> dict[str, str]:
    return {
        "company_id": str(provisioned_org["company_id"]),
        "period_start": "2026-01-01",
        "period_end": "2026-12-31",
    }


@pytest.fixture
def platform_admin_allowlist(
    monkeypatch: pytest.MonkeyPatch,
    provisioned_org: dict,
) -> str:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        email = session.scalar(
            select(User.email).where(User.id == provisioned_org["user_id"])
        )
    assert isinstance(email, str)
    monkeypatch.setattr(settings, "platform_admin_emails", email)
    return email


@pytest.fixture
def stored_files(tmp_path: Path) -> Iterator[LocalPracticeStorage]:
    store = LocalPracticeStorage(tmp_path)
    app.dependency_overrides[get_source_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_source_storage, None)


@pytest.mark.asyncio
async def test_production_hides_product2_from_an_ordinary_owner(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "platform_admin_emails", "founder-only@example.com")
    headers = auth_headers(provisioned_org["token"])

    year_end = await api_client.post(
        "/year-ends",
        headers=headers,
        json=_year_end_body(provisioned_org),
    )
    assert year_end.status_code == 403, year_end.text
    assert year_end.json()["detail"] == _FORBIDDEN

    upload_headers = dict(headers)
    upload_headers["Idempotency-Key"] = "hidden-upload"
    uploaded = await api_client.post(
        "/source-documents",
        headers=upload_headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": ("tb.csv", _CSV.encode(), "text/csv")},
    )
    assert uploaded.status_code == 403, uploaded.text

    beta = await api_client.get("/beta", headers=headers)
    assert beta.status_code == 200, beta.text
    assert beta.json()["acknowledged"] is False
    assert beta.json()["wording_signed_off"] is False

    policy = await api_client.get("/audit-logs/policy", headers=headers)
    assert policy.status_code == 403, policy.text
    audit = await api_client.get("/audit-logs", headers=headers)
    assert audit.status_code == 403, audit.text

    continued = await api_client.post(
        f"/trial-balances/{uuid.uuid4()}/statutory-year-end",
        headers=headers,
        json={"pack_id": "frs102-1a-ie", "pack_version": "2024.09"},
    )
    assert continued.status_code == 403, continued.text

    clients = await api_client.get("/clients?limit=20", headers=headers)
    assert clients.status_code == 200, clients.text


@pytest.mark.asyncio
async def test_production_platform_admin_can_open_a_year_end(
    api_client: AsyncClient,
    provisioned_org: dict,
    platform_admin_allowlist: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del platform_admin_allowlist
    monkeypatch.setattr(settings, "app_env", "production")
    response = await api_client.post(
        "/year-ends",
        headers=auth_headers(provisioned_org["token"]),
        json=_year_end_body(provisioned_org),
    )
    assert response.status_code == 201, response.text
    assert response.json()["pack_id"] == "frs102-1a-ie"


@pytest.mark.asyncio
async def test_development_keeps_product2_on_the_ordinary_owner_role(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "platform_admin_emails", "founder-only@example.com")
    response = await api_client.post(
        "/year-ends",
        headers=auth_headers(provisioned_org["token"]),
        json=_year_end_body(provisioned_org),
    )
    assert response.status_code == 201, response.text


def _other_practice() -> tuple[uuid.UUID, str, str]:
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_other_{suffix}"
    clerk_user_id = f"user_other_{suffix}"
    with SyncSessionLocal() as session:
        other = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name=f"Other Practice {suffix}",
            clerk_user_id=clerk_user_id,
            email=f"other-{suffix}@example.com",
        )
        session.commit()
        org_id = other.organisation.id
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        org_uuid=org_id,
    )
    return org_id, clerk_org_id, token


def _delete_practice(org_id: uuid.UUID) -> None:
    """Remove a practice created only for this test.

    The acknowledgement writes an append-only audit row. Disabling that
    trigger needs the table owner. The parity job logs in as ``findraft``,
    which is not the owner, so this uses the owner session.
    """
    with open_owner_session() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                "ALTER TABLE audit_logs DISABLE TRIGGER findraft_audit_log_append_only"
            )
        )
        try:
            session.execute(
                text("DELETE FROM audit_logs WHERE org_id = :oid"),
                {"oid": str(org_id)},
            )
            session.execute(
                text("DELETE FROM organisations WHERE id = :oid"),
                {"oid": str(org_id)},
            )
            session.commit()
        finally:
            session.execute(
                text(
                    "ALTER TABLE audit_logs ENABLE TRIGGER findraft_audit_log_append_only"
                )
            )
            session.commit()


@pytest.mark.asyncio
async def test_production_acknowledgement_opens_only_that_practice(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "platform_admin_emails", "founder-only@example.com")
    headers = auth_headers(provisioned_org["token"])

    missing = await api_client.post("/beta/acknowledgement", headers=headers)
    assert missing.status_code == 422, missing.text
    unticked = await api_client.post(
        "/beta/acknowledgement",
        headers=headers,
        json={"accepted": False},
    )
    assert unticked.status_code == 422, unticked.text

    _, _, member_token = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="gate-member",
    )
    member_refused = await api_client.post(
        "/beta/acknowledgement",
        headers=auth_headers(member_token),
        json=_ACCEPTED,
    )
    assert member_refused.status_code == 403, member_refused.text

    _, _, admin_token = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="admin",
        email_prefix="gate-admin",
    )
    recorded = await api_client.post(
        "/beta/acknowledgement",
        headers=auth_headers(admin_token),
        json=_ACCEPTED,
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["recorded"] is True
    assert recorded.json()["wording_signed_off"] is False

    year_end = await api_client.post(
        "/year-ends",
        headers=headers,
        json=_year_end_body(provisioned_org),
    )
    assert year_end.status_code == 201, year_end.text
    year_end_id = year_end.json()["id"]

    _, _, viewer_token = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="viewer",
        email_prefix="gate-viewer",
    )
    visible = await api_client.get(
        f"/year-ends/{year_end_id}",
        headers=auth_headers(viewer_token),
    )
    assert visible.status_code == 200, visible.text

    finalise = f"/year-ends/{year_end_id}/drafts/{uuid.uuid4()}/finalise"
    member_final = await api_client.post(
        finalise,
        headers={**auth_headers(member_token), "Idempotency-Key": "member-final"},
        json={"row_version": 1},
    )
    assert member_final.status_code == 403, member_final.text
    owner_final = await api_client.post(
        finalise,
        headers={**headers, "Idempotency-Key": "owner-final"},
        json={"row_version": 1},
    )
    assert owner_final.status_code != 403, owner_final.text

    other_org_id, _, other_token = _other_practice()
    try:
        other_headers = auth_headers(other_token)
        other_year_end = await api_client.post(
            "/year-ends",
            headers=other_headers,
            json=_year_end_body(provisioned_org),
        )
        assert other_year_end.status_code == 403, other_year_end.text
        hidden = await api_client.get(
            f"/year-ends/{year_end_id}",
            headers=other_headers,
        )
        assert hidden.status_code == 403, hidden.text

        other_ack = await api_client.post(
            "/beta/acknowledgement",
            headers=other_headers,
            json=_ACCEPTED,
        )
        assert other_ack.status_code == 200, other_ack.text
        cross = await api_client.get(
            f"/year-ends/{year_end_id}",
            headers=other_headers,
        )
        assert cross.status_code == 404, cross.text
        stolen = await api_client.post(
            "/year-ends",
            headers=other_headers,
            json=_year_end_body(provisioned_org),
        )
        assert stolen.status_code == 404, stolen.text
    finally:
        _delete_practice(other_org_id)


async def _grant_from_admin(org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        await aset_rls_org_id(session, org_id)
        practice = await session.get(Organisation, org_id)
        assert practice is not None
        practice.product2_acknowledged_at = datetime.now(UTC)
        practice.product2_acknowledged_by_user_id = user_id
        await append_audit_log(
            session,
            org_id=org_id,
            user_id=user_id,
            action="beta_self_review",
            entity_type="organisation",
            entity_id=org_id,
            new_value={
                "wording_signed_off": False,
                "self_review_required": True,
                "filing_included": False,
                "pack_id": "frs102-1a-ie",
                "source": "admin",
            },
        )
        await session.commit()


@pytest.mark.asyncio
async def test_users_me_reports_product2_access(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "platform_admin_emails", "founder-only@example.com")
    headers = auth_headers(provisioned_org["token"])

    closed = await api_client.get("/users/me", headers=headers)
    assert closed.status_code == 200, closed.text
    access = closed.json()["product2_access"]
    assert access["enabled"] is False
    assert access["acknowledged"] is False
    assert access["source"] is None
    assert access["wording_signed_off"] is False

    position = await api_client.get("/beta", headers=headers)
    assert position.status_code == 200, position.text
    assert position.json()["statement"] == BETA_STATEMENT

    recorded = await api_client.post(
        "/beta/acknowledgement", headers=headers, json=_ACCEPTED
    )
    assert recorded.status_code == 200, recorded.text
    opened = await api_client.get("/users/me", headers=headers)
    practice = opened.json()["product2_access"]
    assert practice["enabled"] is True
    assert practice["acknowledged"] is True
    assert practice["source"] == "practice"
    assert practice["wording_signed_off"] is False


@pytest.mark.asyncio
async def test_users_me_marks_an_admin_grant_and_keeps_development_on_the_api(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "platform_admin_emails", "founder-only@example.com")
    headers = auth_headers(provisioned_org["token"])
    closed = await api_client.get("/users/me", headers=headers)
    assert closed.json()["product2_access"]["enabled"] is False
    year_end = await api_client.post(
        "/year-ends",
        headers=headers,
        json=_year_end_body(provisioned_org),
    )
    assert year_end.status_code == 201, year_end.text

    await _grant_from_admin(provisioned_org["org_id"], provisioned_org["user_id"])
    monkeypatch.setattr(settings, "app_env", "production")
    granted = await api_client.get("/users/me", headers=headers)
    assert granted.status_code == 200, granted.text
    access = granted.json()["product2_access"]
    assert access["enabled"] is True
    assert access["acknowledged"] is True
    assert access["source"] == "admin"
    assert access["wording_signed_off"] is False


@pytest.mark.asyncio
async def test_background_import_leaves_the_response_pending_then_lists_lines(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del stored_files
    monkeypatch.setattr(settings, "tb_import_background", True)
    headers = auth_headers(provisioned_org["token"])
    created = await api_client.post(
        "/year-ends",
        headers=headers,
        json=_year_end_body(provisioned_org),
    )
    assert created.status_code == 201, created.text
    year_end_id = created.json()["id"]

    upload_headers = dict(headers)
    upload_headers["Idempotency-Key"] = f"bg-{uuid.uuid4().hex}"
    uploaded = await api_client.post(
        "/source-documents",
        headers=upload_headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": ("tb.csv", _CSV.encode(), "text/csv")},
    )
    assert uploaded.status_code == 201, uploaded.text

    version_headers = dict(headers)
    version_headers["Idempotency-Key"] = f"bg-version-{uuid.uuid4().hex}"
    queued = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions",
        headers=version_headers,
        json={"source_document_id": uploaded.json()["id"]},
    )
    assert queued.status_code == 202, queued.text
    assert queued.json()["status"] == "pending"
    version_id = queued.json()["id"]

    fetched = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}",
        headers=headers,
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["status"] == "ready"

    lines = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/lines",
        headers=headers,
    )
    assert lines.status_code == 200, lines.text
    assert [row["nominal_code"] for row in lines.json()["lines"]] == ["1000", "4000"]

    catalogue = await api_client.get("/year-ends/canonical-lines", headers=headers)
    assert catalogue.status_code == 200, catalogue.text
    assert "CASH" in catalogue.json()["lines"]
    assert "REVENUE" in catalogue.json()["lines"]
