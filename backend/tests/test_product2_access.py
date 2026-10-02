"""Product 2 stays off ordinary production accounts until wording is signed off."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.db import SyncSessionLocal, set_rls_org_id
from app.main import app
from app.models.user import User
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from tests.conftest import auth_headers

_FORBIDDEN = "You don't have permission to access this resource."

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
    assert beta.status_code == 403, beta.text

    policy = await api_client.get("/audit-logs/policy", headers=headers)
    assert policy.status_code == 403, policy.text

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
