"""Week 3: generic TB import, immutable versions, and the prior-year gate."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.main import app
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from app.services.tb_import_worker import process_tb_version
from findraft.engine.reconciliation import check_prior_year_gate
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


def _csv(body: str) -> bytes:
    return body.encode()


async def _year_end(api_client: AsyncClient, provisioned_org: dict) -> str:
    response = await api_client.post(
        "/year-ends",
        headers=auth_headers(provisioned_org["token"]),
        json={
            "company_id": str(provisioned_org["company_id"]),
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _upload(
    api_client: AsyncClient,
    provisioned_org: dict,
    *,
    name: str,
    content: bytes,
    key: str,
    content_type: str,
) -> str:
    headers = auth_headers(provisioned_org["token"])
    headers["Idempotency-Key"] = key
    response = await api_client.post(
        "/source-documents",
        headers=headers,
        data={"company_id": str(provisioned_org["company_id"])},
        files={"file": (name, content, content_type)},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@pytest.mark.asyncio
async def test_import_stays_pending_until_the_worker_and_reimport_is_a_new_draft(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    document_id = await _upload(
        api_client,
        provisioned_org,
        name="tb.xlsx",
        content=balanced_tb_xlsx_bytes(),
        key="tb-file-1",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    headers = auth_headers(provisioned_org["token"])
    headers["Idempotency-Key"] = "import-1"
    created = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions",
        headers=headers,
        json={"source_document_id": document_id},
    )
    assert created.status_code == 202, created.text
    body = created.json()
    assert body["status"] == "pending"
    assert body["draft_version_number"] is None
    version_id = body["id"]

    with SyncSessionLocal() as session:
        count = session.execute(
            text("SELECT count(*) FROM findraft_tb_lines WHERE tb_version_id = :id"),
            {"id": version_id},
        ).scalar_one()
        assert count == 0
        processed = process_tb_version(
            session,
            org_id=provisioned_org["org_id"],
            version_id=uuid.UUID(version_id),
            storage=stored_files,
        )
        assert processed is not None
        assert processed.status == "ready"

    fetched = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}",
        headers=auth_headers(provisioned_org["token"]),
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["status"] == "ready"
    assert fetched.json()["draft_version_number"] == 1

    formula = await _upload(
        api_client,
        provisioned_org,
        name="formula.csv",
        content=_csv(
            "Account Code,Account Name,Debit,Credit\n"
            "1000,=Director loan,10.00,0.00\n"
            "2000,Sales,0.00,10.00\n"
        ),
        key="tb-file-2",
        content_type="text/csv",
    )
    headers["Idempotency-Key"] = "import-2"
    second = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions",
        headers=headers,
        json={"source_document_id": formula},
    )
    assert second.status_code == 202, second.text
    second_id = second.json()["id"]
    assert second.json()["version_number"] == 2
    with SyncSessionLocal() as session:
        processed = process_tb_version(
            session,
            org_id=provisioned_org["org_id"],
            version_id=uuid.UUID(second_id),
            storage=stored_files,
        )
        assert processed is not None and processed.status == "ready"
        set_rls_org_id(session, provisioned_org["org_id"])
        name = session.execute(
            text(
                """
                SELECT account_name FROM findraft_tb_lines
                WHERE tb_version_id = :id AND nominal_code = '1000'
                """
            ),
            {"id": second_id},
        ).scalar_one()
        assert name == "'=Director loan"
        drafts = session.execute(
            text(
                """
                SELECT version_number, tb_version_id
                FROM findraft_draft_versions
                WHERE year_end_id = :id
                ORDER BY version_number
                """
            ),
            {"id": year_end_id},
        ).all()
        assert [(row.version_number, str(row.tb_version_id)) for row in drafts] == [
            (1, version_id),
            (2, second_id),
        ]
        with pytest.raises(Exception, match="immutable"):
            session.execute(
                text(
                    "UPDATE findraft_tb_versions SET status = 'failed' WHERE id = :id"
                ),
                {"id": version_id},
            )
        session.rollback()


@pytest.mark.asyncio
async def test_unbalanced_import_fails_and_does_not_create_a_draft(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    document_id = await _upload(
        api_client,
        provisioned_org,
        name="unbalanced.csv",
        content=_csv("Account Code,Account Name,Debit,Credit\n1000,Cash,10.00,0.00\n"),
        key="unbalanced",
        content_type="text/csv",
    )
    headers = auth_headers(provisioned_org["token"])
    headers["Idempotency-Key"] = "import-bad"
    created = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions",
        headers=headers,
        json={"source_document_id": document_id},
    )
    assert created.status_code == 202, created.text
    version_id = created.json()["id"]
    with SyncSessionLocal() as session:
        processed = process_tb_version(
            session,
            org_id=provisioned_org["org_id"],
            version_id=uuid.UUID(version_id),
            storage=stored_files,
        )
        assert processed is not None
        assert processed.status == "failed"
        drafts = session.execute(
            text(
                "SELECT count(*) FROM findraft_draft_versions WHERE year_end_id = :id"
            ),
            {"id": year_end_id},
        ).scalar_one()
        assert drafts == 0


@pytest.mark.asyncio
async def test_prior_year_gate_blocks_until_manual_entry_or_first_period(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    del stored_files
    year_end_id = await _year_end(api_client, provisioned_org)
    headers = auth_headers(provisioned_org["token"])
    blocked = await api_client.get(
        f"/year-ends/{year_end_id}/reconciliation-gate",
        headers=headers,
    )
    assert blocked.status_code == 200, blocked.text
    engine_block = check_prior_year_gate(False)
    assert engine_block is not None
    assert blocked.json()["open"] is False
    assert blocked.json()["code"] == engine_block.code
    assert blocked.json()["severity"] == engine_block.severity
    assert blocked.json()["message"] == engine_block.message

    unknown = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json={"lines": [{"canonical_line": "DIRECTOR_LOAN", "amount": "10.00"}]},
    )
    assert unknown.status_code == 400, unknown.text

    loose = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json={"lines": [{"canonical_line": "CASH", "amount": "10.005"}]},
    )
    assert loose.status_code == 400, loose.text

    confirmed = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json={"lines": [{"canonical_line": "CASH", "amount": "10.00"}]},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["prior_year_validated"] is True
    assert confirmed.json()["lines"] == [{"canonical_line": "CASH", "amount": "10.00"}]

    opened = await api_client.get(
        f"/year-ends/{year_end_id}/reconciliation-gate",
        headers=headers,
    )
    assert opened.json()["open"] is True
    assert check_prior_year_gate(True) is None

    again = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json={"lines": [{"canonical_line": "CASH", "amount": "11.00"}]},
    )
    assert again.status_code == 409, again.text


@pytest.mark.asyncio
async def test_first_financial_period_opens_the_gate_without_comparatives(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    headers = auth_headers(provisioned_org["token"])
    marked = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["first_financial_period"] is True
    assert marked.json()["prior_year_validated"] is True
    gate = await api_client.get(
        f"/year-ends/{year_end_id}/reconciliation-gate",
        headers=headers,
    )
    assert gate.json()["open"] is True
    rejected = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json={"lines": [{"canonical_line": "REVENUE", "amount": "1.00"}]},
    )
    assert rejected.status_code == 409, rejected.text


@pytest.mark.asyncio
async def test_pack_rejects_a_period_before_effective_from(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    response = await api_client.post(
        "/year-ends",
        headers=auth_headers(provisioned_org["token"]),
        json={
            "company_id": str(provisioned_org["company_id"]),
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
        },
    )
    assert response.status_code == 400, response.text
    assert "2026-01-01" in response.json()["detail"]


@pytest.mark.asyncio
async def test_viewer_cannot_import(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    del stored_files
    year_end_id = await _year_end(api_client, provisioned_org)
    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="tb-viewer",
    )
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="owner",
        org_uuid=provisioned_org["org_id"],
    )
    _set_role(org_id=provisioned_org["org_id"], user_id=user_id, role="viewer")
    response = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions",
        headers={
            **auth_headers(token),
            "Idempotency-Key": "viewer-import",
        },
        json={"source_document_id": str(uuid.uuid4())},
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == _FORBIDDEN


def test_request_handler_does_not_parse_the_workbook() -> None:
    source = Path("/workspace/backend/app/routers/year_ends.py").read_text()
    assert "openpyxl" not in source
    assert "parse_tb_file" not in source
