"""Week 8 statutory statements, autoescape, and the deny-all PDF fetcher."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.main import app
from app.services.fa_import_worker import process_fa_version
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from app.services.statutory_statements import (
    StatementEntity,
    StatementRow,
    StatutoryStatements,
    build_statutory_statements,
    deny_external_fetch,
    rounding_flag_for_lines,
    write_statement_pdf,
)
from findraft.engine.money import money
from findraft.engine.rounding import flag_for_note
from findraft.engine.statements import SOFP_COMPLIANCE_STATEMENT
from tests.conftest import auth_headers, make_access_token
from tests.test_fa_ingestion import _csv_bytes
from tests.test_organisations_api import _add_org_user
from tests.test_reconciliation import (
    _FA_REGISTER,
    _MAPPINGS,
    _TB,
    _TINY,
    _golden_csv,
    _import_csv,
    _lines,
    _mapping_payload,
)
from tests.test_role_enforcement import _set_role
from tests.test_tb_ingestion import _upload, _year_end

_FORBIDDEN = "You don't have permission to access this resource."
_NOT_RENDERABLE = "Statutory statements are not renderable"
_OFFICE = "<script>alert(1)</script>"
_INJECTED = "{{7*7}}"


@pytest.fixture
def stored_files(tmp_path: Path) -> Iterator[LocalPracticeStorage]:
    store = LocalPracticeStorage(tmp_path)
    app.dependency_overrides[get_source_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_source_storage, None)


def _entity(**overrides: str) -> StatementEntity:
    values = {
        "name": "Northwind Limited",
        "registered_office": "1 Harbour Road, Dublin",
        "company_number": "123456",
        "directors_list": "Ada Lovelace",
        "currency": "EUR",
        "average_employees": "",
    }
    values.update(overrides)
    return StatementEntity(**values)


def _golden(
    *,
    entity: StatementEntity | None = None,
    disclosure_flags: dict[str, bool] | None = None,
    practice_name: str = "",
) -> StatutoryStatements:
    return build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines(_TB),
        mappings=_MAPPINGS,
        prior_retained_earnings=Decimal("-322062.00"),
        prior_canonical={
            "FA_PLANT_COST": Decimal("111400.00"),
            "RETAINED_EARNINGS": Decimal("-322062.00"),
        },
        fa_register=_FA_REGISTER,
        entity=entity or _entity(),
        period_start="2025-01-01",
        period_end="2025-12-31",
        disclosure_flags=disclosure_flags,
        practice_name=practice_name,
    )


def _row(rows: tuple[StatementRow, ...], label: str) -> StatementRow:
    return next(row for row in rows if row.label == label)


def test_golden_render_keeps_engine_figures_and_zero_lines() -> None:
    document = _golden()
    assert document.renderable is True
    assert document.watermark == "DRAFT"
    assert document.blocked is False
    assert document.build_error is None
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert document.compliance_statement == SOFP_COMPLIANCE_STATEMENT
    assert document.html is not None
    profit_row = _row(document.income, "Profit for the financial year")
    assert profit_row.current == document.profit
    assert _row(document.sofp, "Net assets").current == document.net_assets
    assert _row(document.sofp, "Profit and loss account").current == Decimal(
        "455712.00"
    )
    assert _row(document.sofp, "Intangible assets").current == Decimal("0.00")
    assert _row(document.sofp, "Right-of-use assets").current == Decimal("0.00")
    assert _row(document.sofp, "Stocks").current == Decimal("0.00")
    codes = [note.code for note in document.notes]
    assert codes == [
        "N0_ENTITY",
        "N1_POLICIES",
        "N2_FA",
        "N3_DEBTORS",
        "N4_CREDITORS",
        "N5_LOANS",
        "N6_CAPITAL",
        "N7_RPT",
        "N8_EMPLOYEES",
        "N9_COMMITMENTS",
    ]
    policies = next(note for note in document.notes if note.code == "N1_POLICIES")
    assert "nearest whole unit" in policies.body
    assert "euro" in policies.body
    assert "{{life_plant}}" in policies.body
    assert "Short-term employee benefits" not in policies.body
    assert "Revenue is recognised" in policies.body
    fa_note = next(note for note in document.notes if note.code == "N2_FA")
    total = next(row for row in fa_note.fa_rows if row.asset_class == "Total")
    assert total.nbv_close == Decimal("134000.00")
    debtors = next(note for note in document.notes if note.code == "N3_DEBTORS")
    trade = next(line for line in debtors.lines if line.line == "TRADE_DEBTORS")
    assert trade.current == Decimal("245800.00")
    flag = next(
        item
        for item in document.rounding_flags
        if item.statement_line_id == "N3_DEBTORS.total"
    )
    children = [line.current for line in debtors.lines]
    expected = flag_for_note(
        children, sum(children, Decimal("0")), Decimal("1"), flag.statement_line_id
    )
    assert flag.flagged is False
    assert flag.flagged == expected["flagged"]
    assert flag.gap == expected["gap"]
    assert flag.deeplink is None
    assert flag.deeplink == expected["deeplink"]
    html = document.html
    for snippet in (
        "DRAFT",
        "455,812",
        "157,650",
        "Profit for the financial year",
        "3. Fixed assets",
        "4. Debtors",
        "Trade debtors",
        SOFP_COMPLIANCE_STATEMENT,
        "{{life_plant}}",
        "nearest whole unit",
        "euro",
    ):
        assert snippet in html
    for hidden in (
        "<td>Intangible assets</td>",
        "<td>Right-of-use assets</td>",
        "<td>Stocks</td>",
        "455812.00",
        "157650.00",
    ):
        assert hidden not in html
    assert "N2_FA" not in html
    assert "N3_DEBTORS" not in html
    assert "TRADE_DEBTORS" not in html
    assert "statement of changes in retained earnings" not in html.lower()
    assert "V-BANK-001" not in {item.code for item in document.checks}
    pdf = write_statement_pdf(html)
    assert pdf.startswith(b"%PDF")


def test_rounding_flag_matches_the_engine_gap() -> None:
    aggregated = {
        "TRADE_DEBTORS": Decimal("1.40"),
        "OTHER_DEBTORS": Decimal("1.40"),
    }
    flag = rounding_flag_for_lines(
        note_code="N3_DEBTORS",
        line_names=["TRADE_DEBTORS", "OTHER_DEBTORS"],
        aggregated=aggregated,
    )
    children = [money(Decimal("1.40")), money(Decimal("1.40"))]
    expected = flag_for_note(
        children,
        money(sum(children, Decimal("0"))),
        Decimal("1"),
        "N3_DEBTORS.total",
    )
    assert flag.flagged is True
    assert flag.flagged == expected["flagged"]
    assert flag.gap == expected["gap"]
    assert flag.deeplink == expected["deeplink"]
    assert flag.gap == Decimal("-1")


def test_company_fields_are_escaped_and_not_executed() -> None:
    document = _golden(
        entity=_entity(
            name=_INJECTED,
            registered_office=_OFFICE,
            directors_list=_OFFICE,
        )
    )
    assert document.html is not None
    html = document.html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert _INJECTED in html
    entity_note = next(note for note in document.notes if note.code == "N0_ENTITY")
    assert _OFFICE in entity_note.body


def test_closed_gate_unmapped_critical_and_build_error_withhold_the_draft(
    tmp_path: Path,
) -> None:
    closed = build_statutory_statements(
        prior_year_validated=False,
        tb_lines=[],
        mappings={},
        prior_retained_earnings=Decimal("0"),
        entity=_entity(),
    )
    assert closed.renderable is False
    assert closed.blocked is True
    assert closed.sofp == ()
    assert closed.html is None
    assert [item.code for item in closed.checks] == ["V-GATE-001"]

    unmapped = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines((("1200", "Bank", 100, 0), ("3000", "Capital", 0, 100))),
        mappings={"1200": "CASH"},
        prior_retained_earnings=Decimal("0"),
        entity=_entity(),
    )
    assert unmapped.renderable is False
    assert unmapped.sofp == ()
    assert unmapped.html is None
    assert [item.code for item in unmapped.checks] == ["V-TB-001", "V-MAP-001"]

    loans = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines((("1200", "Bank", 100, 0), ("9000", "Loans", 0, 100))),
        mappings={"1200": "CASH", "9000": "LOANS"},
        prior_retained_earnings=Decimal("0"),
        entity=_entity(),
    )
    assert loans.renderable is False
    assert loans.build_error is not None
    assert "LOANS" in loans.build_error
    assert loans.sofp == ()
    assert loans.html is None

    rules = tmp_path / "review-rules.json"
    rules.write_text(
        '{"rules":[{"id":"R-BROKEN-001","scope":"client","severity":"WARNING",'
        '"when":"not_a_real_input > 0","message":"should not pass"}]}',
        encoding="utf-8",
    )
    broken = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines((("2130", "Bank", 100, 0), ("3000", "Share capital", 0, 100))),
        mappings={"2130": "CASH", "3000": "SHARE_CAPITAL"},
        prior_retained_earnings=Decimal("0"),
        pack_rules_path=rules,
        entity=_entity(),
    )
    assert broken.renderable is False
    assert broken.html is None
    assert broken.sofp == ()
    failed = next(item for item in broken.checks if item.code == "R-BROKEN-001")
    assert failed.passed is False
    assert failed.severity == "CRITICAL"

    dividend = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines(
            (
                ("2130", "Bank", 20, 0),
                ("8500", "Dividends", 80, 0),
                ("3000", "Share capital", 0, 100),
            )
        ),
        mappings={"2130": "CASH", "8500": "DIVIDENDS", "3000": "SHARE_CAPITAL"},
        prior_retained_earnings=Decimal("0"),
        entity=_entity(),
    )
    assert dividend.renderable is False
    assert dividend.html is None
    critical = next(item for item in dividend.checks if item.code == "R-DIV-001")
    assert critical.severity == "CRITICAL"


def test_warning_does_not_block_a_draft_without_a_register() -> None:
    document = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines((("1500", "Plant", 100, 0), ("3000", "Capital", 0, 100))),
        mappings={"1500": "FA_PLANT_COST", "3000": "SHARE_CAPITAL"},
        prior_retained_earnings=Decimal("0"),
        entity=_entity(),
    )
    assert document.renderable is True
    assert document.html is not None
    fa = next(item for item in document.checks if item.code == "V-FA-001")
    assert fa.passed is False
    assert fa.severity == "WARNING"
    assert _row(document.sofp, "Tangible assets").current == Decimal("100.00")
    assert _row(document.sofp, "Stocks").current == Decimal("0.00")
    assert "DRAFT" in document.html


def test_url_fetcher_refuses_remote_and_file_urls() -> None:
    with pytest.raises(
        ValueError, match="external fetch refused: https://example.invalid/a.png"
    ):
        deny_external_fetch("https://example.invalid/a.png")
    with pytest.raises(ValueError, match="external fetch refused: file:///etc/passwd"):
        deny_external_fetch("file:///etc/passwd", timeout=1, ssl_context=None)
    pdf = write_statement_pdf("<html><body><p>DRAFT</p></body></html>")
    assert pdf.startswith(b"%PDF")
    with pytest.raises(ValueError, match="external fetch refused"):
        write_statement_pdf(
            '<html><body><img src="https://example.invalid/x.png" alt=""></body></html>'
        )


def _statements_path(year_end_id: str, version_id: str) -> str:
    return f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/statements"


async def _ready_golden(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
    year_end_id: str,
) -> str:
    version_id = await _import_csv(
        api_client,
        provisioned_org,
        stored_files,
        year_end_id=year_end_id,
        name="golden.csv",
        content=_golden_csv(),
        file_key="stmt-golden-file",
        version_key="stmt-golden-version",
        process=True,
    )
    headers = auth_headers(provisioned_org["token"])
    prior = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json={
            "lines": [
                {"canonical_line": "FA_PLANT_COST", "amount": "111400.00"},
                {"canonical_line": "RETAINED_EARNINGS", "amount": "-322062.00"},
            ]
        },
    )
    assert prior.status_code == 200, prior.text
    fa_document = await _upload(
        api_client,
        provisioned_org,
        name="fa.csv",
        content=_csv_bytes(),
        key="stmt-fa-file",
        content_type="text/csv",
    )
    fa_headers = auth_headers(provisioned_org["token"])
    fa_headers["Idempotency-Key"] = "stmt-fa-version"
    queued = await api_client.post(
        f"/year-ends/{year_end_id}/fixed-asset-versions",
        headers=fa_headers,
        json={"source_document_id": fa_document},
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
        # process_fa_version commits, which clears the transaction-local org id.
        set_rls_org_id(session, provisioned_org["org_id"])
        session.execute(
            text(
                "UPDATE companies SET registered_office = :office, "
                "company_number = :number, directors = CAST(:directors AS jsonb) "
                "WHERE id = :id"
            ),
            {
                "office": _OFFICE,
                "number": "654321",
                "directors": '[{"name": "Ada Lovelace"}]',
                "id": str(provisioned_org["company_id"]),
            },
        )
        session.commit()
    confirmed = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json=_mapping_payload(_MAPPINGS),
    )
    assert confirmed.status_code == 200, confirmed.text
    return version_id


@pytest.mark.asyncio
async def test_api_golden_render_and_pdf(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    version_id = await _ready_golden(
        api_client, provisioned_org, stored_files, year_end_id
    )
    headers = auth_headers(provisioned_org["token"])
    captured: list[str] = []
    real_pdf = write_statement_pdf

    def _capture(html: str) -> bytes:
        captured.append(html)
        return real_pdf(html)

    monkeypatch.setattr("app.routers.year_ends.write_statement_pdf", _capture)
    body = await api_client.get(
        _statements_path(year_end_id, version_id), headers=headers
    )
    assert body.status_code == 200, body.text
    payload = body.json()
    assert payload["watermark"] == "DRAFT"
    assert payload["renderable"] is True
    assert payload["net_assets"] == "455812.00"
    assert payload["profit"] == "157650.00"
    assert payload["compliance_statement"] == SOFP_COMPLIANCE_STATEMENT
    labels = [row["label"] for row in payload["sofp"]]
    assert "Intangible assets" in labels
    assert "Right-of-use assets" in labels
    assert "Stocks" in labels
    stocks = next(row for row in payload["sofp"] if row["label"] == "Stocks")
    assert stocks["current"] == "0.00"
    income_profit = next(
        row
        for row in payload["income"]
        if row["label"] == "Profit for the financial year"
    )
    assert income_profit["current"] == payload["profit"]
    assert [
        note["code"]
        for note in payload["notes"]
        if note["code"] in ("N2_FA", "N3_DEBTORS")
    ] == [
        "N2_FA",
        "N3_DEBTORS",
    ]
    entity = next(note for note in payload["notes"] if note["code"] == "N0_ENTITY")
    assert _OFFICE in entity["body"]
    flag = next(
        item
        for item in payload["rounding_flags"]
        if item["statement_line_id"] == "N3_DEBTORS.total"
    )
    assert flag["flagged"] is False
    assert Decimal(flag["gap"]) == Decimal("0")
    assert flag["deeplink"] is None
    pdf = await api_client.get(
        f"{_statements_path(year_end_id, version_id)}.pdf", headers=headers
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert captured
    assert "<script>" not in captured[0]
    assert "&lt;script&gt;" in captured[0]
    assert "DRAFT" in captured[0]
    assert "455,812" in captured[0]
    assert "455812.00" not in captured[0]
    assert "as at 31 December 2026" in captured[0]
    assert "for the year ended 31 December 2026" in captured[0]
    assert "2026 £" in captured[0]
    assert "2025 £" in captured[0]


@pytest.mark.asyncio
async def test_api_withholds_closed_unmapped_and_pending_pdf(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    headers = auth_headers(provisioned_org["token"])
    pending = await _import_csv(
        api_client,
        provisioned_org,
        stored_files,
        year_end_id=year_end_id,
        name="tiny.csv",
        content=_TINY.encode(),
        file_key="stmt-gate-file",
        version_key="stmt-gate-version",
        process=False,
    )
    closed = await api_client.get(
        _statements_path(year_end_id, pending), headers=headers
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["renderable"] is False
    assert closed.json()["blocked"] is True
    assert closed.json()["sofp"] == []
    assert [item["code"] for item in closed.json()["checks"]] == ["V-GATE-001"]
    closed_pdf = await api_client.get(
        f"{_statements_path(year_end_id, pending)}.pdf",
        headers=headers,
    )
    assert closed_pdf.status_code == 400, closed_pdf.text
    assert closed_pdf.json()["detail"] == _NOT_RENDERABLE

    opened = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert opened.status_code == 200, opened.text
    still_pending = await api_client.get(
        _statements_path(year_end_id, pending), headers=headers
    )
    assert still_pending.status_code == 400, still_pending.text
    assert still_pending.json()["detail"] == "Trial balance version is not ready"

    ready = await _import_csv(
        api_client,
        provisioned_org,
        stored_files,
        year_end_id=year_end_id,
        name="tiny.csv",
        content=_TINY.encode(),
        file_key="stmt-unmap-file",
        version_key="stmt-unmap-version",
        process=True,
    )
    unmapped = await api_client.get(
        _statements_path(year_end_id, ready), headers=headers
    )
    assert unmapped.status_code == 200, unmapped.text
    assert unmapped.json()["renderable"] is False
    assert unmapped.json()["sofp"] == []
    assert [(item["code"], item["passed"]) for item in unmapped.json()["checks"]] == [
        ("V-TB-001", True),
        ("V-MAP-001", False),
    ]
    unmapped_pdf = await api_client.get(
        f"{_statements_path(year_end_id, ready)}.pdf",
        headers=headers,
    )
    assert unmapped_pdf.status_code == 400, unmapped_pdf.text
    assert unmapped_pdf.json()["detail"] == _NOT_RENDERABLE


@pytest.mark.asyncio
async def test_viewer_can_read_statements_and_other_year_end_is_hidden(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    version_id = await _import_csv(
        api_client,
        provisioned_org,
        stored_files,
        year_end_id=year_end_id,
        name="tiny.csv",
        content=_TINY.encode(),
        file_key="stmt-viewer-file",
        version_key="stmt-viewer-version",
        process=False,
    )
    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="stmt-viewer",
    )
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="owner",
        org_uuid=provisioned_org["org_id"],
    )
    _set_role(org_id=provisioned_org["org_id"], user_id=user_id, role="viewer")
    viewer = auth_headers(token)
    readable = await api_client.get(
        _statements_path(year_end_id, version_id), headers=viewer
    )
    assert readable.status_code == 200, readable.text
    assert readable.json()["blocked"] is True
    refused = await api_client.get(
        f"{_statements_path(year_end_id, version_id)}.pdf",
        headers=viewer,
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"] == _NOT_RENDERABLE
    assert refused.json()["detail"] != _FORBIDDEN

    headers = auth_headers(provisioned_org["token"])
    missing = await api_client.get(
        _statements_path(str(uuid.uuid4()), str(uuid.uuid4())),
        headers=headers,
    )
    assert missing.status_code == 404, missing.text
    second = await api_client.post(
        "/year-ends",
        headers=headers,
        json={
            "company_id": str(provisioned_org["company_id"]),
            "period_start": "2026-01-01",
            "period_end": "2026-06-30",
        },
    )
    assert second.status_code == 201, second.text
    other = await api_client.get(
        _statements_path(str(second.json()["id"]), version_id),
        headers=headers,
    )
    assert other.status_code == 404, other.text
    other_pdf = await api_client.get(
        f"{_statements_path(str(second.json()['id']), version_id)}.pdf",
        headers=headers,
    )
    assert other_pdf.status_code == 404, other_pdf.text


@pytest.mark.asyncio
async def test_warning_api_still_renders(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    headers = auth_headers(provisioned_org["token"])
    marked = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert marked.status_code == 200, marked.text
    version_id = await _import_csv(
        api_client,
        provisioned_org,
        stored_files,
        year_end_id=year_end_id,
        name="plant.csv",
        content=(
            "Account Code,Account Name,Debit,Credit\n"
            "1500,Plant,100.00,0.00\n"
            "3000,Called up share capital,0.00,100.00\n"
        ).encode(),
        file_key="stmt-plant-file",
        version_key="stmt-plant-version",
        process=True,
    )
    confirmed = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json=_mapping_payload({"1500": "FA_PLANT_COST", "3000": "SHARE_CAPITAL"}),
    )
    assert confirmed.status_code == 200, confirmed.text
    report = await api_client.get(
        _statements_path(year_end_id, version_id), headers=headers
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["renderable"] is True
    assert body["watermark"] == "DRAFT"
    fa = next(item for item in body["checks"] if item["code"] == "V-FA-001")
    assert fa["passed"] is False
    tangible = next(row for row in body["sofp"] if row["label"] == "Tangible assets")
    assert tangible["current"] == "100.00"
    pdf = await api_client.get(
        f"{_statements_path(year_end_id, version_id)}.pdf", headers=headers
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF")
