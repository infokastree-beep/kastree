"""Source-document upload API: auth, idempotency, and per-practice storage."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.main import app
from app.models.client import Client
from app.models.company import Company
from app.services.org_provisioning import provision_first_signup
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from tests.conftest import auth_headers, balanced_tb_xlsx_bytes, make_access_token
from tests.test_organisations_api import _add_org_user
from tests.test_role_enforcement import _set_role

_FORBIDDEN = "You don't have permission to access this resource."


@pytest.fixture
def stored_files(tmp_path: Path) -> Iterator[LocalPracticeStorage]:
    store = LocalPracticeStorage(tmp_path)
    app.dependency_overrides[get_source_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_source_storage, None)


def _pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"


@pytest.mark.asyncio
async def test_member_upload_stores_under_the_practice_prefix(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    headers["Idempotency-Key"] = "upload-1"
    response = await api_client.post(
        "/source-documents",
        headers=headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": ("notes.pdf", _pdf(), "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["detected_type"] == "pdf"
    assert body["original_filename"] == "notes.pdf"
    assert body["byte_size"] == len(_pdf())
    assert "storage_key" not in body

    keys = stored_files.list_keys()
    assert len(keys) == 1
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    assert keys[0].startswith(f"practices/{org_id}/companies/{company_id}/documents/")
    assert stored_files.get(key=keys[0]) == _pdf()

    replay = await api_client.post(
        "/source-documents",
        headers=headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": ("notes.pdf", _pdf(), "application/pdf")},
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == body["id"]
    assert stored_files.list_keys() == keys

    fetched = await api_client.get(
        f"/source-documents/{body['id']}",
        headers=auth_headers(provisioned_org["token"]),
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["sha256"] == body["sha256"]


@pytest.mark.asyncio
async def test_same_idempotency_key_rejects_a_different_file(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    del stored_files
    headers = auth_headers(provisioned_org["token"])
    headers["Idempotency-Key"] = "once"
    first = await api_client.post(
        "/source-documents",
        headers=headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": ("a.pdf", _pdf(), "application/pdf")},
    )
    assert first.status_code == 201, first.text
    second = await api_client.post(
        "/source-documents",
        headers=headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": ("b.csv", b"code,name\n", "text/csv")},
    )
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_rejects_macro_workbook_and_mismatched_type(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    del stored_files
    headers = auth_headers(provisioned_org["token"])
    headers["Idempotency-Key"] = "macro"
    rejected = await api_client.post(
        "/source-documents",
        headers=headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={
            "file": (
                "tb.xlsm",
                balanced_tb_xlsx_bytes(),
                "application/vnd.ms-excel.sheet.macroEnabled.12",
            )
        },
    )
    assert rejected.status_code == 400, rejected.text
    assert "Macro-enabled" in rejected.json()["detail"]

    headers["Idempotency-Key"] = "mismatch"
    mismatch = await api_client.post(
        "/source-documents",
        headers=headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": ("tb.xlsx", _pdf(), "application/pdf")},
    )
    assert mismatch.status_code == 400, mismatch.text
    assert mismatch.json()["detail"] == "File type does not match its contents"


@pytest.mark.asyncio
async def test_missing_idempotency_key_is_rejected(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    del stored_files
    response = await api_client.post(
        "/source-documents",
        headers=auth_headers(provisioned_org["token"]),
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": ("a.pdf", _pdf(), "application/pdf")},
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Idempotency-Key is required"


@pytest.mark.asyncio
async def test_viewer_cannot_upload_and_other_practice_cannot_read(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    del stored_files
    owner_headers = auth_headers(provisioned_org["token"])
    owner_headers["Idempotency-Key"] = "owner-file"
    created = await api_client.post(
        "/source-documents",
        headers=owner_headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": ("a.pdf", _pdf(), "application/pdf")},
    )
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]

    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="src-viewer",
    )
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="owner",
        org_uuid=provisioned_org["org_id"],
    )
    member_headers = auth_headers(token)
    member_headers["Idempotency-Key"] = "member-file"
    member_upload = await api_client.post(
        "/source-documents",
        headers=member_headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": ("b.csv", b"code,name\n1,Cash\n", "text/csv")},
    )
    assert member_upload.status_code == 201, member_upload.text

    _set_role(org_id=provisioned_org["org_id"], user_id=user_id, role="viewer")
    viewer_headers = auth_headers(token)
    viewer_headers["Idempotency-Key"] = "viewer-file"
    denied = await api_client.post(
        "/source-documents",
        headers=viewer_headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": ("c.pdf", _pdf(), "application/pdf")},
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"] == _FORBIDDEN

    readable = await api_client.get(
        f"/source-documents/{document_id}",
        headers=auth_headers(token),
    )
    assert readable.status_code == 200, readable.text

    other = await api_client.get(
        f"/source-documents/{document_id}",
        headers=auth_headers(provisioned_org["token"]),
    )
    assert other.status_code == 200

    missing = await api_client.get(
        f"/source-documents/{uuid.uuid4()}",
        headers=auth_headers(provisioned_org["token"]),
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
def _remove_org(org_id: uuid.UUID) -> None:
    with SyncSessionLocal() as session:
        session.execute(text("RESET ROLE"))
        oid = str(org_id)
        session.execute(
            text("DELETE FROM findraft_source_documents WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text(
                "DELETE FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)"
            ),
            {"oid": oid},
        )
        session.execute(text("DELETE FROM clients WHERE org_id = :oid"), {"oid": oid})
        session.execute(
            text("DELETE FROM notifications WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(text("DELETE FROM users WHERE org_id = :oid"), {"oid": oid})
        session.execute(
            text("DELETE FROM subscription_events WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"),
            {"oid": oid},
        )
        session.commit()


@pytest.mark.asyncio
async def test_another_practice_cannot_read_or_upload_for_the_company(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    del stored_files
    headers = auth_headers(provisioned_org["token"])
    headers["Idempotency-Key"] = "practice-a"
    created = await api_client.post(
        "/source-documents",
        headers=headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": ("a.pdf", _pdf(), "application/pdf")},
    )
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]

    suffix = uuid.uuid4().hex[:10]
    with SyncSessionLocal() as session:
        provisioned = provision_first_signup(
            session,
            clerk_org_id=f"org_other_{suffix}",
            org_name=f"Other {suffix}",
            clerk_user_id=f"user_other_{suffix}",
            email=f"other-{suffix}@example.com",
            role="owner",
        )
        set_rls_org_id(session, provisioned.organisation.id)
        client = Client(org_id=provisioned.organisation.id, name="Other client")
        session.add(client)
        session.flush()
        company = Company(
            client_id=client.id,
            name="Other company",
            functional_currency="EUR",
        )
        session.add(company)
        session.commit()
        other_org_id = provisioned.organisation.id
        other_token = make_access_token(
            clerk_user_id=f"user_other_{suffix}",
            clerk_org_id=f"org_other_{suffix}",
            org_uuid=other_org_id,
        )
    try:
        other_headers = auth_headers(other_token)
        hidden = await api_client.get(
            f"/source-documents/{document_id}",
            headers=other_headers,
        )
        assert hidden.status_code == 404, hidden.text
        other_headers["Idempotency-Key"] = "practice-b"
        denied = await api_client.post(
            "/source-documents",
            headers=other_headers,
            data={"company_id": str(provisioned_org["company_id"])},
            files={"file": ("b.pdf", _pdf(), "application/pdf")},
        )
        assert denied.status_code == 404, denied.text
    finally:
        _remove_org(other_org_id)


@pytest.mark.asyncio
async def test_unknown_company_is_not_found(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    del stored_files
    headers = auth_headers(provisioned_org["token"])
    headers["Idempotency-Key"] = "foreign-company"
    response = await api_client.post(
        "/source-documents",
        headers=headers,
        data={"company_id": str(uuid.uuid4())},
        files={"file": ("a.pdf", _pdf(), "application/pdf")},
    )
    assert response.status_code == 404, response.text
