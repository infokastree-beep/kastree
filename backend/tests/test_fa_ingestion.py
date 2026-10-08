"""Week 4: fixed-asset register import and the small-company size test."""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy import text

from app.db import SyncSessionLocal
from app.main import app
from app.services.fa_import_worker import process_fa_version
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from findraft.engine.notes import build_fa_grid
from findraft.engine.pack import load_manifest, pack_dir
from findraft.engine.reconciliation import check_prior_year_gate
from tests.conftest import auth_headers, make_access_token
from tests.test_organisations_api import _add_org_user
from tests.test_role_enforcement import _set_role
from tests.test_tb_ingestion import _upload, _year_end

_FORBIDDEN = "You don't have permission to access this resource."

_CSV = (
    "class,opening_cost,additions,disposals,disposals_dep,opening_dep,charge\n"
    "=Plant,120000.00,30000.00,0.00,0.00,35600.00,16400.00\n"
    "Motor vehicles,45000.00,15000.00,0.00,0.00,18000.00,6000.00\n"
)


def _csv_bytes(body: str = _CSV) -> bytes:
    return body.encode()


def _xlsx_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(
        ["class", "opening_cost", "additions", "disposals", "opening_dep", "charge"]
    )
    sheet.append(["Fixtures", 100, 20, 0, 40, 10])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def stored_files(tmp_path: Path) -> Iterator[LocalPracticeStorage]:
    store = LocalPracticeStorage(tmp_path)
    app.dependency_overrides[get_source_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_source_storage, None)


def _set_currency(company_id: uuid.UUID, currency: str) -> None:
    with SyncSessionLocal() as session:
        session.execute(
            text("UPDATE companies SET functional_currency = :currency WHERE id = :id"),
            {"currency": currency, "id": str(company_id)},
        )
        session.commit()


async def _queue(
    api_client: AsyncClient,
    provisioned_org: dict,
    year_end_id: str,
    document_id: str,
    key: str,
) -> str:
    headers = auth_headers(provisioned_org["token"])
    headers["Idempotency-Key"] = key
    response = await api_client.post(
        f"/year-ends/{year_end_id}/fixed-asset-versions",
        headers=headers,
        json={"source_document_id": document_id},
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "pending"
    return str(response.json()["id"])


@pytest.mark.asyncio
async def test_register_stays_pending_until_the_worker_and_reimport_is_a_new_version(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    document_id = await _upload(
        api_client,
        provisioned_org,
        name="fa.csv",
        content=_csv_bytes(),
        key="fa-src-1",
        content_type="text/csv",
    )
    version_id = await _queue(
        api_client, provisioned_org, year_end_id, document_id, "fa-1"
    )
    with SyncSessionLocal() as session:
        processed = process_fa_version(
            session,
            org_id=provisioned_org["org_id"],
            version_id=uuid.UUID(version_id),
            storage=stored_files,
        )
        assert processed is not None and processed.status == "ready"
        name = session.execute(
            text(
                """
                SELECT asset_class FROM findraft_fa_lines
                WHERE fa_version_id = :id AND line_no = 1
                """
            ),
            {"id": version_id},
        ).scalar_one()
        assert name == "'=Plant"
    headers = auth_headers(provisioned_org["token"])
    ready = await api_client.get(
        f"/year-ends/{year_end_id}/fixed-asset-versions/{version_id}",
        headers=headers,
    )
    assert ready.status_code == 200, ready.text
    body = ready.json()
    assert body["invariant_holds"] is True
    engine = build_fa_grid(
        {
            "'=Plant": {
                "opening_cost": Decimal("120000.00"),
                "additions": Decimal("30000.00"),
                "disposals": Decimal("0.00"),
                "disposals_dep": Decimal("0.00"),
                "opening_dep": Decimal("35600.00"),
                "charge": Decimal("16400.00"),
            },
            "Motor vehicles": {
                "opening_cost": Decimal("45000.00"),
                "additions": Decimal("15000.00"),
                "disposals": Decimal("0.00"),
                "disposals_dep": Decimal("0.00"),
                "opening_dep": Decimal("18000.00"),
                "charge": Decimal("6000.00"),
            },
        }
    )
    total = next(row for row in engine if row.get("class") == "Total")
    assert body["total"]["nbv_close"] == format(total["nbv_close"], "f")
    assert engine[-1]["invariant_holds"] is True

    second_document = await _upload(
        api_client,
        provisioned_org,
        name="fa-2.csv",
        content=_csv_bytes(
            "class,opening_cost,additions,disposals,opening_dep,charge\n"
            "Fixtures,10.00,0.00,0.00,0.00,0.00\n"
        ),
        key="fa-src-2",
        content_type="text/csv",
    )
    second_id = await _queue(
        api_client, provisioned_org, year_end_id, second_document, "fa-2"
    )
    with SyncSessionLocal() as session:
        processed = process_fa_version(
            session,
            org_id=provisioned_org["org_id"],
            version_id=uuid.UUID(second_id),
            storage=stored_files,
        )
        assert processed is not None and processed.status == "ready"
        drafts = session.execute(
            text(
                "SELECT count(*) FROM findraft_draft_versions WHERE year_end_id = :id"
            ),
            {"id": year_end_id},
        ).scalar_one()
        assert drafts == 0
        with pytest.raises(Exception, match="immutable"):
            session.execute(
                text(
                    "UPDATE findraft_fa_versions SET status = 'failed' WHERE id = :id"
                ),
                {"id": version_id},
            )
        session.rollback()
    again = await api_client.get(
        f"/year-ends/{year_end_id}/fixed-asset-versions/{version_id}",
        headers=headers,
    )
    assert again.json()["status"] == "ready"
    assert again.json()["version_number"] == 1


@pytest.mark.asyncio
async def test_bad_register_fails_and_xlsx_import_uses_the_engine_grid(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    bad_id = await _upload(
        api_client,
        provisioned_org,
        name="bad.csv",
        content=_csv_bytes("account,amount\nCash,10.00\n"),
        key="fa-bad-src",
        content_type="text/csv",
    )
    version_id = await _queue(
        api_client, provisioned_org, year_end_id, bad_id, "fa-bad"
    )
    with SyncSessionLocal() as session:
        processed = process_fa_version(
            session,
            org_id=provisioned_org["org_id"],
            version_id=uuid.UUID(version_id),
            storage=stored_files,
        )
        assert processed is not None and processed.status == "failed"
        lines = session.execute(
            text("SELECT count(*) FROM findraft_fa_lines WHERE fa_version_id = :id"),
            {"id": version_id},
        ).scalar_one()
        assert lines == 0

    sheet_id = await _upload(
        api_client,
        provisioned_org,
        name="fa.xlsx",
        content=_xlsx_bytes(),
        key="fa-xlsx-src",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    xlsx_version = await _queue(
        api_client, provisioned_org, year_end_id, sheet_id, "fa-xlsx"
    )
    with SyncSessionLocal() as session:
        processed = process_fa_version(
            session,
            org_id=provisioned_org["org_id"],
            version_id=uuid.UUID(xlsx_version),
            storage=stored_files,
        )
        assert processed is not None and processed.status == "ready"
    ready = await api_client.get(
        f"/year-ends/{year_end_id}/fixed-asset-versions/{xlsx_version}",
        headers=auth_headers(provisioned_org["token"]),
    )
    assert ready.json()["lines"][0]["asset_class"] == "Fixtures"
    assert ready.json()["total"]["nbv_close"] == "70.00"
    assert ready.json()["invariant_holds"] is True


@pytest.mark.asyncio
async def test_size_eligibility_uses_the_pack_thresholds(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    manifest = load_manifest(pack_dir("frs102-1a-ie", "2024.09") / "pack.json")
    thresholds = manifest["thresholds"]
    assert thresholds == {
        "regime": "small",
        "currency": "EUR",
        "rule": "2-of-3",
        "years": "current-and-preceding",
        "turnover": "15000000.00",
        "balance_sheet": "7500000.00",
        "employees": 50,
    }
    year_end_id = await _year_end(api_client, provisioned_org)
    headers = auth_headers(provisioned_org["token"])
    inside = {
        "turnover": "1000000.00",
        "balance_sheet_total": "500000.00",
        "employees": 10,
    }
    gbp = await api_client.post(
        f"/year-ends/{year_end_id}/size-eligibility",
        headers=headers,
        json={"current": inside, "preceding": inside},
    )
    assert gbp.status_code == 400, gbp.text
    assert "EUR" in gbp.json()["detail"]

    _set_currency(provisioned_org["company_id"], "EUR")
    at_limit = {
        "turnover": "15000000.01",
        "balance_sheet_total": "7500000.00",
        "employees": 50,
    }
    eligible = await api_client.post(
        f"/year-ends/{year_end_id}/size-eligibility",
        headers=headers,
        json={"current": at_limit, "preceding": inside},
    )
    assert eligible.status_code == 200, eligible.text
    assert eligible.json()["eligible"] is True
    assert eligible.json()["current_conditions_met"] == 2
    assert eligible.json()["preceding_conditions_met"] == 3
    gate = await api_client.get(
        f"/year-ends/{year_end_id}/reconciliation-gate",
        headers=headers,
    )
    assert gate.json()["open"] is False
    assert check_prior_year_gate(False) is not None

    over = {
        "turnover": "15000000.01",
        "balance_sheet_total": "7500000.01",
        "employees": 51,
    }
    blocked = await api_client.post(
        f"/year-ends/{year_end_id}/size-eligibility",
        headers=headers,
        json={"current": over, "preceding": inside},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["eligible"] is False
    assert blocked.json()["current_conditions_met"] == 0
    stored = await api_client.get(
        f"/year-ends/{year_end_id}/size-eligibility",
        headers=headers,
    )
    assert stored.json()["eligible"] is False
    assert stored.json()["message"] == blocked.json()["message"]

    missing = await api_client.post(
        f"/year-ends/{year_end_id}/size-eligibility",
        headers=headers,
        json={"current": inside},
    )
    assert missing.status_code == 400, missing.text

    marked = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert marked.status_code == 200, marked.text
    first = await api_client.post(
        f"/year-ends/{year_end_id}/size-eligibility",
        headers=headers,
        json={"current": inside},
    )
    assert first.status_code == 200, first.text
    assert first.json()["eligible"] is True
    assert first.json()["preceding_conditions_met"] is None


@pytest.mark.asyncio
async def test_viewer_cannot_import_a_register_or_check_size(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="fa-viewer",
    )
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="owner",
        org_uuid=provisioned_org["org_id"],
    )
    _set_role(org_id=provisioned_org["org_id"], user_id=user_id, role="viewer")
    response = await api_client.post(
        f"/year-ends/{year_end_id}/fixed-asset-versions",
        headers={**auth_headers(token), "Idempotency-Key": "viewer-fa"},
        json={"source_document_id": str(uuid.uuid4())},
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == _FORBIDDEN
    size = await api_client.post(
        f"/year-ends/{year_end_id}/size-eligibility",
        headers=auth_headers(token),
        json={
            "current": {
                "turnover": "1.00",
                "balance_sheet_total": "1.00",
                "employees": 1,
            },
            "preceding": {
                "turnover": "1.00",
                "balance_sheet_total": "1.00",
                "employees": 1,
            },
        },
    )
    assert size.status_code == 403, size.text
    assert size.json()["detail"] == _FORBIDDEN


def test_request_handler_does_not_parse_the_register() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "app" / "routers" / "year_ends.py"
    ).read_text(encoding="utf-8")
    assert "openpyxl" not in source
    assert "read_spreadsheet_text" not in source
    assert "read_csv_text" not in source
    assert "process_fa_version" not in source
