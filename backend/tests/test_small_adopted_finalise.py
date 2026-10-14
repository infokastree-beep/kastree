"""Finalise small adopted drafts through the HTTP route.

The production image stores this service under ``/app/app`` and the engine
under ``/app/findraft/engine``. A fixed parent count looks above that image.
These tests keep the evidence lineage check, and finalise the small files a
practice actually uploads.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.config import settings
from app.db import SyncSessionLocal, set_rls_org_id
from app.main import app
from app.services.draft_workflow import (
    ENGINE_FILES_MISSING,
    DraftRejected,
    engine_directory,
    engine_files_missing_message,
    engine_sha,
)
from app.services.fa_import_worker import process_fa_version
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from app.services.statutory_evidence import build_evidence_lines
from app.services.statutory_statements import StatementRow
from tests.conftest import auth_headers
from tests.test_adopted_trial_balance import (
    _answer_all_no,
    _draft_version,
    _insert_tb,
    _set_file_hash,
    _snapshot,
)
from tests.test_fa_ingestion import _csv_bytes
from tests.test_tb_ingestion import _upload

_Row = tuple[str, str, str, str, str, str]

_SMALL: tuple[_Row, ...] = (
    ("1000", "Cash at Bank", "30000.00", "0.00", "30000.00", "cash"),
    ("1100", "Trade Debtors", "20000.00", "0.00", "20000.00", "trade_receivables"),
    ("2000", "Trade Creditors", "0.00", "15000.00", "-15000.00", "trade_payables"),
    ("3000", "Share Capital", "0.00", "10000.00", "-10000.00", "share_capital"),
    ("4000", "Sales Revenue", "0.00", "100000.00", "-100000.00", "revenue"),
    ("5000", "Cost of Sales", "40250.00", "0.00", "40250.00", "cost_of_sales"),
    ("6000", "Operating Expenses", "34750.00", "0.00", "34750.00", "operating_expenses"),
)

_ADMIN = {"6000": "ADMIN_EXPENSES"}


def _login_role() -> tuple[str, bool, bool]:
    with SyncSessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT current_user, r.rolsuper, r.rolbypassrls
                FROM pg_roles AS r
                WHERE r.rolname = current_user
                """
            )
        ).one()
    print(
        f"executing_role={row[0]} rolsuper={row[1]} rolbypassrls={row[2]}",
        flush=True,
    )
    return str(row[0]), bool(row[1]), bool(row[2])


def _without(rows: tuple[_Row, ...], code: str) -> tuple[_Row, ...]:
    return tuple(row for row in rows if row[0] != code)


def _eur_company(org_id: uuid.UUID, company_id: uuid.UUID) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text("UPDATE companies SET functional_currency = 'EUR' WHERE id = :id"),
            {"id": str(company_id)},
        )
        session.commit()


@pytest.fixture
def stored_files(tmp_path: Path) -> Iterator[LocalPracticeStorage]:
    store = LocalPracticeStorage(tmp_path)
    app.dependency_overrides[get_source_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_source_storage, None)


def _set_statutory(
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    lines: dict[str, str],
) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        for code, statutory in lines.items():
            session.execute(
                text(
                    "UPDATE account_mappings SET statutory_line = :line "
                    "WHERE company_id = :company AND source_code = :code"
                ),
                {"line": statutory, "company": str(company_id), "code": code},
            )
        session.commit()


async def _letterhead(
    api_client: AsyncClient,
    headers: dict[str, str],
    year_end_id: str,
    org_id: uuid.UUID,
) -> None:
    saved = await api_client.put(
        f"/year-ends/{year_end_id}/company-details",
        headers=headers,
        json={
            "registered_office": "1 Harbour Street, Dublin",
            "company_number": "AB123456",
            "incorporated_on": "2026-01-01",
            "principal_activity": "Software",
            "secretary": "Charles Babbage",
            "directors": [{"name": "Ada Lovelace"}],
        },
    )
    assert saved.status_code == 200, saved.text
    from tests.directors_report_http import save_nil_directors_report

    await save_nil_directors_report(
        api_client,
        headers,
        year_end_id,
        directors=["Ada Lovelace"],
        secretary="Charles Babbage",
    )
    approved = await api_client.put(
        f"/year-ends/{year_end_id}/approval",
        headers=headers,
        json={
            "approval_date": "2027-03-15",
            "signing_directors": ["Ada Lovelace"],
        },
    )
    assert approved.status_code == 200, approved.text
    from tests.evidence_exemption import record_evidenced_exemption

    record_evidenced_exemption(org_id, year_end_id)
    from tests.compilation_http import save_compilation_report

    await save_compilation_report(api_client, headers, year_end_id)


async def _open_small(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
    rows: tuple[_Row, ...],
    *,
    statutory: dict[str, str],
    key: str,
) -> tuple[str, str, dict[str, str]]:
    role, _superuser, _bypass = _login_role()
    assert role == "findraft"
    _eur_company(provisioned_org["org_id"], provisioned_org["company_id"])
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "platform_admin_emails", "")
    headers = auth_headers(provisioned_org["token"])
    acknowledged = await api_client.post(
        "/beta/acknowledgement",
        headers=headers,
        json={"accepted": True},
    )
    assert acknowledged.status_code == 200, acknowledged.text
    tb_id = _insert_tb(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        rows=rows,
        period_start=date(2026, 1, 1),
    )
    _set_file_hash(tb_id, provisioned_org["org_id"], "ab" * 32)
    if statutory:
        _set_statutory(
            org_id=provisioned_org["org_id"],
            company_id=provisioned_org["company_id"],
            lines=statutory,
        )
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = str(opened.json()["year_end_id"])
    period = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert period.status_code == 200, period.text
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    draft_id = str(draft.json()["draft_id"])
    await _letterhead(api_client, headers, year_end_id, provisioned_org["org_id"])
    _answer_all_no(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        draft_id=draft_id,
    )
    board = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/dashboard",
        headers=headers,
    )
    assert board.status_code == 200, board.text
    assert board.json()["can_finalise"] is True, board.text
    finalised = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/finalise",
        headers={**headers, "Idempotency-Key": key},
        json={"row_version": _draft_version(draft_id, provisioned_org["org_id"])},
    )
    assert finalised.status_code == 200, finalised.text
    assert finalised.json()["status"] == "final"
    return year_end_id, draft_id, headers


def test_production_image_layout_finds_the_engine(tmp_path: Path) -> None:
    """The image layout is ``/app/app/services`` beside ``/app/findraft/engine``."""
    services = tmp_path / "app" / "services"
    services.mkdir(parents=True)
    marker = services / "draft_workflow.py"
    marker.write_text("# deployed module\n", encoding="utf-8")
    engine = tmp_path / "findraft" / "engine"
    engine.mkdir(parents=True)
    (engine / "money.py").write_text("TOLERANCE = 0\n", encoding="utf-8")
    assert engine_directory(marker) == engine
    missed = marker.resolve().parents[3] / "findraft" / "engine"
    assert list(missed.glob("*.py")) == []


def test_missing_engine_directory_stays_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.draft_workflow.engine_directory",
        lambda start=None: None,
    )
    with pytest.raises(DraftRejected, match="accounts calculation files") as caught:
        engine_sha()
    assert caught.value.detail == ENGINE_FILES_MISSING
    year_end_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    message = engine_files_missing_message(year_end_id)
    assert "engine sources" not in message
    assert "/year-ends/11111111-1111-4111-8111-111111111111/draft?section=trial-balance" in message
    assert "/year-ends/11111111-1111-4111-8111-111111111111/draft?section=company-details" in message


def test_zero_face_row_with_no_accounts_still_has_to_tie() -> None:
    """A blank line is valid only when it adds to the printed amount, including zero."""
    tied = build_evidence_lines(
        tb_lines=[],
        mappings={},
        sofp=(
            StatementRow(
                label="Cash at bank and in hand",
                current=Decimal("0.00"),
                prior=None,
            ),
        ),
        income=(),
    )
    assert tied[0].amount == Decimal("0.00")
    assert tied[0].accounts == ()
    with pytest.raises(ValueError, match="evidence does not tie"):
        build_evidence_lines(
            tb_lines=[],
            mappings={},
            sofp=(
                StatementRow(
                    label="Cash at bank and in hand",
                    current=Decimal("10.00"),
                    prior=None,
                ),
            ),
            income=(),
        )


def test_evidence_lineage_is_still_required(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import statutory_evidence as evidence

    monkeypatch.setattr(evidence, "aggregate", lambda *_args, **_kwargs: {})
    with pytest.raises(ValueError, match="evidence sources are missing"):
        evidence.build_evidence_lines(
            tb_lines=[],
            mappings={},
            sofp=(),
            income=(),
        )


@pytest.mark.asyncio
async def test_small_first_period_file_finalises(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cash 30000, debtors 20000, creditors 15000, capital 10000, sales 100000, cost 40250, admin 34750."""
    _year_end_id, draft_id, _headers = await _open_small(
        api_client,
        provisioned_org,
        monkeypatch,
        _SMALL,
        statutory=_ADMIN,
        key="small-first-period",
    )
    stored = _snapshot(draft_id, provisioned_org["org_id"])
    assert stored is not None
    statement = stored["statement"]
    assert isinstance(statement, dict)
    assert statement["net_assets"] == "35000.00"
    assert statement["profit"] == "25000.00"


@pytest.mark.asyncio
async def test_small_file_without_engine_files_names_the_pages(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.draft_workflow.engine_directory",
        lambda start=None: None,
    )
    role, _superuser, _bypass = _login_role()
    assert role == "findraft"
    _eur_company(provisioned_org["org_id"], provisioned_org["company_id"])
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "platform_admin_emails", "")
    headers = auth_headers(provisioned_org["token"])
    acknowledged = await api_client.post(
        "/beta/acknowledgement",
        headers=headers,
        json={"accepted": True},
    )
    assert acknowledged.status_code == 200, acknowledged.text
    tb_id = _insert_tb(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        rows=_SMALL,
        period_start=date(2026, 1, 1),
    )
    _set_statutory(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        lines=_ADMIN,
    )
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = str(opened.json()["year_end_id"])
    period = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert period.status_code == 200, period.text
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    draft_id = str(draft.json()["draft_id"])
    await _letterhead(api_client, headers, year_end_id, provisioned_org["org_id"])
    _answer_all_no(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        draft_id=draft_id,
    )
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/finalise",
        headers={**headers, "Idempotency-Key": "small-missing-engine"},
        json={"row_version": _draft_version(draft_id, provisioned_org["org_id"])},
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"] == engine_files_missing_message(uuid.UUID(year_end_id))
    assert "engine sources" not in refused.text


@pytest.mark.asyncio
async def test_finalise_without_creditors(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _without(_SMALL, "2000")
    cash = ("1000", "Cash at Bank", "15000.00", "0.00", "15000.00", "cash")
    rows = (cash, *(row for row in rows if row[0] != "1000"))
    await _open_small(
        api_client,
        provisioned_org,
        monkeypatch,
        rows,
        statutory=_ADMIN,
        key="small-no-creditors",
    )


@pytest.mark.asyncio
async def test_finalise_one_revenue_line(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _open_small(
        api_client,
        provisioned_org,
        monkeypatch,
        (
            ("1000", "Cash at Bank", "100.00", "0.00", "100.00", "cash"),
            ("4000", "Sales Revenue", "0.00", "100.00", "-100.00", "revenue"),
        ),
        statutory={},
        key="small-revenue-only",
    )


@pytest.mark.asyncio
async def test_finalise_with_fixed_assets_and_a_register(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
    stored_files: LocalPracticeStorage,
) -> None:
    role, _superuser, _bypass = _login_role()
    assert role == "findraft"
    _eur_company(provisioned_org["org_id"], provisioned_org["company_id"])
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "platform_admin_emails", "")
    headers = auth_headers(provisioned_org["token"])
    acknowledged = await api_client.post(
        "/beta/acknowledgement",
        headers=headers,
        json={"accepted": True},
    )
    assert acknowledged.status_code == 200, acknowledged.text
    rows: tuple[_Row, ...] = (
        ("1500", "Plant and machinery", "10000.00", "0.00", "10000.00", "property_plant_equipment"),
        ("1505", "Accumulated depreciation", "0.00", "2000.00", "-2000.00", "property_plant_equipment"),
        ("7000", "Depreciation", "2000.00", "0.00", "2000.00", "depreciation"),
        ("1000", "Cash at Bank", "10000.00", "0.00", "10000.00", "cash"),
        ("3000", "Share Capital", "0.00", "10000.00", "-10000.00", "share_capital"),
        ("4000", "Sales Revenue", "0.00", "10000.00", "-10000.00", "revenue"),
    )
    tb_id = _insert_tb(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        rows=rows,
        period_start=date(2026, 1, 1),
    )
    _set_statutory(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        lines={
            "1500": "FA_PLANT_COST",
            "1505": "FA_ACCUM_DEP",
            "7000": "DEPRECIATION_CHARGE",
        },
    )
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = str(opened.json()["year_end_id"])
    period = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert period.status_code == 200, period.text
    register = (
        "class,opening_cost,additions,disposals,disposals_dep,opening_dep,charge\n"
        "Plant,0.00,10000.00,0.00,0.00,0.00,2000.00\n"
    )
    document_id = await _upload(
        api_client,
        provisioned_org,
        name="fa.csv",
        content=_csv_bytes(register),
        key="small-fa-file",
        content_type="text/csv",
    )
    queued = await api_client.post(
        f"/year-ends/{year_end_id}/fixed-asset-versions",
        headers={**headers, "Idempotency-Key": "small-fa-version"},
        json={"source_document_id": document_id},
    )
    assert queued.status_code == 202, queued.text
    with SyncSessionLocal() as session:
        processed = process_fa_version(
            session,
            org_id=provisioned_org["org_id"],
            version_id=uuid.UUID(str(queued.json()["id"])),
            storage=stored_files,
        )
        assert processed is not None
        assert processed.status == "ready"
        session.commit()
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    draft_id = str(draft.json()["draft_id"])
    await _letterhead(api_client, headers, year_end_id, provisioned_org["org_id"])
    _answer_all_no(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        draft_id=draft_id,
    )
    board = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/dashboard",
        headers=headers,
    )
    assert board.status_code == 200, board.text
    assert board.json()["can_finalise"] is True, board.text
    finalised = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/finalise",
        headers={**headers, "Idempotency-Key": "small-fixed-assets"},
        json={"row_version": _draft_version(draft_id, provisioned_org["org_id"])},
    )
    assert finalised.status_code == 200, finalised.text


@pytest.mark.asyncio
async def test_finalise_with_a_dividend(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _open_small(
        api_client,
        provisioned_org,
        monkeypatch,
        (
            ("1000", "Cash at Bank", "20000.00", "0.00", "20000.00", "cash"),
            ("3000", "Share Capital", "0.00", "10000.00", "-10000.00", "share_capital"),
            ("4000", "Sales Revenue", "0.00", "20000.00", "-20000.00", "revenue"),
            ("6000", "Operating Expenses", "5000.00", "0.00", "5000.00", "operating_expenses"),
            ("8500", "Dividends", "5000.00", "0.00", "5000.00", "dividends"),
        ),
        statutory=_ADMIN,
        key="small-dividend",
    )


@pytest.mark.asyncio
async def test_finalise_without_debtors(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = tuple(
        ("4000", "Sales Revenue", "0.00", "80000.00", "-80000.00", "revenue")
        if row[0] == "4000"
        else row
        for row in _without(_SMALL, "1100")
    )
    await _open_small(
        api_client,
        provisioned_org,
        monkeypatch,
        rows,
        statutory=_ADMIN,
        key="small-no-debtors",
    )


@pytest.mark.asyncio
async def test_finalise_a_loss(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _year_end_id, draft_id, _headers = await _open_small(
        api_client,
        provisioned_org,
        monkeypatch,
        (
            ("1000", "Cash at Bank", "40000.00", "0.00", "40000.00", "cash"),
            ("3000", "Share Capital", "0.00", "50000.00", "-50000.00", "share_capital"),
            ("4000", "Sales Revenue", "0.00", "10000.00", "-10000.00", "revenue"),
            ("6000", "Operating Expenses", "20000.00", "0.00", "20000.00", "operating_expenses"),
        ),
        statutory=_ADMIN,
        key="small-loss",
    )
    stored = _snapshot(draft_id, provisioned_org["org_id"])
    assert stored is not None
    statement = stored["statement"]
    assert isinstance(statement, dict)
    assert statement["profit"] == "-10000.00"
    assert statement["net_assets"] == "40000.00"
