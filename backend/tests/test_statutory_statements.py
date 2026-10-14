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
    NoteParticulars,
    StatementEntity,
    ShareClassFact,
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
    share_classes: tuple[ShareClassFact, ...] = (),
    note_library: object | None = None,
    audit_exemption_claimed: bool | None = None,
    note_particulars: NoteParticulars | None = None,
    first_financial_period: bool = False,
    interim_dividend: Decimal | None = None,
    recommended_dividend: Decimal | None = None,
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
        share_classes=share_classes,
        note_library=note_library,
        audit_exemption_claimed=audit_exemption_claimed,
        note_particulars=note_particulars,
        first_financial_period=first_financial_period,
        interim_dividend=interim_dividend,
        recommended_dividend=recommended_dividend,
    )


def _row(rows: tuple[StatementRow, ...], label: str) -> StatementRow:
    return next(row for row in rows if row.label == label)


def test_note_sign_convention_matches_the_face_in_absolute_value() -> None:
    """Creditor notes are positive. Brackets stay on the face."""
    document = _golden()
    assert document.html is not None
    pairs = (
        (
            "N4_CREDITORS",
            ("Creditors: amounts falling due within one year",),
        ),
        (
            "N3_DEBTORS",
            ("Trade debtors", "Other debtors"),
        ),
    )
    for code, labels in pairs:
        note = next(item for item in document.notes if item.code == code)
        face_total = sum(
            (_row(document.sofp, label).current for label in labels),
            Decimal("0"),
        )
        note_total = sum((line.current for line in note.lines), Decimal("0"))
        assert note_total == abs(face_total)
        prior_face = sum(
            (_row(document.sofp, label).prior or Decimal("0") for label in labels),
            Decimal("0"),
        )
        prior_note = sum((line.prior for line in note.lines), Decimal("0"))
        assert prior_note == abs(prior_face)
    creditors = next(item for item in document.notes if item.code == "N4_CREDITORS")
    assert all(line.current >= 0 for line in creditors.lines)
    trade = next(line for line in creditors.lines if line.line == "TRADE_CREDITORS")
    assert trade.current == Decimal("67200.00")
    face = _row(document.sofp, "Creditors: amounts falling due within one year")
    assert face.current < 0
    assert "(110,500)" in document.html
    assert "(67,200)" not in document.html
    assert "67,200" in document.html


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
    assert 'id="note-N2_FA"' in html
    assert 'id="note-N3_DEBTORS"' in html
    visible = html.replace('id="note-N2_FA"', "").replace('id="note-N3_DEBTORS"', "")
    assert "N2_FA" not in visible
    assert "N3_DEBTORS" not in visible
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
            "matches_filed_accounts": True,
            "lines": [
                {"canonical_line": "CASH", "amount": "322062.00"},
                {"canonical_line": "RETAINED_EARNINGS", "amount": "-322062.00"},
            ],
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
                "company_number = :number, principal_activity = :activity, "
                "directors = CAST(:directors AS jsonb) "
                "WHERE id = :id"
            ),
            {
                "office": _OFFICE,
                "number": "654321",
                "activity": "Software",
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


def test_retained_earnings_statement_when_share_capital_is_unchanged() -> None:
    """Opening, profit, dividends, and closing. The golden totals stay put."""
    from datetime import date

    from app.services.statutory_compose import compose_pdf_html

    document = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines(_TB),
        mappings=_MAPPINGS,
        prior_retained_earnings=Decimal("-322062.00"),
        prior_canonical={
            "FA_PLANT_COST": Decimal("111400.00"),
            "RETAINED_EARNINGS": Decimal("-322062.00"),
            "SHARE_CAPITAL": Decimal("-100.00"),
        },
        fa_register=_FA_REGISTER,
        entity=_entity(),
        period_start="2025-01-01",
        period_end="2025-12-31",
    )
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert [row.label for row in document.retained_earnings] == [
        "Retained earnings at the beginning of the period",
        "Profit for the financial year",
        "Dividends",
        "Retained earnings at the end of the period",
    ]
    assert [row.current for row in document.retained_earnings] == [
        Decimal("322062.00"),
        Decimal("157650.00"),
        Decimal("-24000.00"),
        Decimal("455712.00"),
    ]
    opening, profit_row, dividends, closing = document.retained_earnings
    assert opening.current + profit_row.current + dividends.current == closing.current
    assert document.html is not None
    block = document.html.split("Statement of income and retained earnings", 1)[1]
    assert block.index(
        "Retained earnings at the beginning of the period"
    ) < block.index("Dividends")
    assert "(24,000)" in block
    assert "455,712" in block
    composed = compose_pdf_html(
        document,
        report_setup=None,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        first_financial_period=False,
    )
    assert ">Statement of income and retained earnings</h2>" in composed
    contents = composed.split('data-section="contents"', 1)[1].split(
        'data-section="', 1
    )[0]
    assert "Statement of income and retained earnings" in contents
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_golden_omits_retained_earnings_when_share_capital_changed() -> None:
    document = _golden()
    assert document.retained_earnings == ()
    assert document.html is not None
    assert "Statement of income and retained earnings" not in document.html
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_dividend_note_uses_recorded_amounts_not_the_trial_balance_line() -> None:
    """1AD.35 prints a recorded nil or the recorded amounts. No new total."""
    from dataclasses import replace
    from datetime import date

    from app.services.beta import WORDING_BANNER
    from app.services.statutory_compose import compose_pdf_html, docx_presentation

    blank = _golden()
    assert "N10_DIVIDENDS" not in {note.code for note in blank.notes}
    half = _golden(interim_dividend=Decimal("1000.00"))
    assert "N10_DIVIDENDS" not in {note.code for note in half.notes}

    nil = _golden(
        interim_dividend=Decimal("0.00"),
        recommended_dividend=Decimal("0.00"),
    )
    nil_note = next(note for note in nil.notes if note.code == "N10_DIVIDENDS")
    assert nil_note.title == f"{len(nil.notes)}. Dividends"
    assert nil_note.body == (
        "No dividend was paid during the financial year and the directors "
        "do not recommend a dividend."
    )
    assert "24,000" not in nil_note.body
    assert "1AD" not in nil_note.body
    assert nil.net_assets == Decimal("455812.00")
    assert nil.profit == Decimal("157650.00")
    assert nil.retained_earnings == ()

    paid = _golden(
        interim_dividend=Decimal("1000.50"),
        recommended_dividend=Decimal("-10.00"),
    )
    paid_note = next(note for note in paid.notes if note.code == "N10_DIVIDENDS")
    assert (
        "An interim dividend of €1,000.50 was paid during the financial year."
        in paid_note.body
    )
    assert "A dividend of (€10.00) is recommended." in paid_note.body
    assert "24,000" not in paid_note.body
    assert "1AD" not in paid_note.body
    assert paid.net_assets == Decimal("455812.00")
    assert paid.profit == Decimal("157650.00")

    one_nil = _golden(
        interim_dividend=Decimal("0"),
        recommended_dividend=Decimal("250.00"),
    )
    one_nil_note = next(note for note in one_nil.notes if note.code == "N10_DIVIDENDS")
    assert (
        "No interim dividend was paid during the financial year." in one_nil_note.body
    )
    assert "A dividend of €250.00 is recommended." in one_nil_note.body
    assert "24,000" not in one_nil_note.body

    composed = compose_pdf_html(
        paid,
        report_setup=None,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        first_financial_period=False,
        currency="EUR",
    )
    assert "€1,000.50" in composed
    assert "optional for a small entity" not in composed
    header, _signature = docx_presentation(
        replace(paid, watermark="FINAL"),
        report_setup=None,
        approval_date=None,
        signing_directors=[],
    )
    assert header == f"DRAFT {WORDING_BANNER}"
    assert WORDING_BANNER == (
        "Statutory wording not yet reviewed by a qualified reviewer"
    )


def test_taxation_note_defaults_off_and_ties_to_the_face() -> None:
    """Optional for a small entity. The two figures are copied from the face."""
    from app.services.statutory_display import format_whole

    off = _golden()
    assert "N11_TAXATION" not in {note.code for note in off.notes}
    assert off.net_assets == Decimal("455812.00")
    assert off.profit == Decimal("157650.00")

    document = _golden(note_library={"omitted": [], "added": ["taxation_note"]})
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    note = next(item for item in document.notes if item.code == "N11_TAXATION")
    assert note.title == f"{len(document.notes)}. Taxation"
    tax = next(row for row in document.income if row.label == "Tax on profit")
    creditors = next(item for item in document.notes if item.code == "N4_CREDITORS")
    corp = next(line for line in creditors.lines if line.line == "CORP_TAX")
    assert tax.prior is not None
    assert format_whole(tax.current) in note.body
    assert format_whole(tax.prior) in note.body
    assert format_whole(corp.current) in note.body
    assert format_whole(corp.prior) in note.body
    assert "reconcil" not in note.body.casefold()
    assert "1AD" not in note.body
    assert "optional for a small entity" not in note.body
    assert document.html is not None
    assert note.body.split("\n\n")[0] in document.html
    assert document.added_blocks == ("taxation_note",)


def test_stocks_carrying_amount_stays_off_and_ties_to_the_face() -> None:
    """Optional line under the stocks policy. The amount is the face amount."""
    from app.services.statutory_display import format_whole

    quiet = _golden(note_library={"omitted": [], "added": ["stocks_carrying_amount"]})
    policies = next(note for note in quiet.notes if note.code == "N1_POLICIES")
    assert "carrying amount" not in policies.body
    assert quiet.net_assets == Decimal("455812.00")
    assert quiet.profit == Decimal("157650.00")

    shifted = []
    for code, name, debit, credit in _TB:
        if code == "2130":
            debit -= 1000
        shifted.append((code, name, debit, credit))
    shifted.append(("1000", "Stocks", 1000, 0))
    mappings = dict(_MAPPINGS)
    mappings["1000"] = "STOCKS"

    def _render(added: bool) -> StatutoryStatements:
        library = (
            {"omitted": [], "added": ["stocks_carrying_amount"]} if added else None
        )
        return build_statutory_statements(
            prior_year_validated=True,
            tb_lines=_lines(tuple(shifted)),
            mappings=mappings,
            prior_retained_earnings=Decimal("-322062.00"),
            prior_canonical={
                "FA_PLANT_COST": Decimal("111400.00"),
                "RETAINED_EARNINGS": Decimal("-322062.00"),
            },
            fa_register=_FA_REGISTER,
            entity=_entity(),
            period_start="2025-01-01",
            period_end="2025-12-31",
            note_library=library,
        )

    plain = _render(False)
    stocks = next(row for row in plain.sofp if row.label == "Stocks")
    assert stocks.current == Decimal("1000.00")
    plain_policies = next(note for note in plain.notes if note.code == "N1_POLICIES")
    assert "Stocks are stated at the lower of cost" in plain_policies.body
    assert "carrying amount" not in plain_policies.body
    assert plain.net_assets == Decimal("455812.00")
    assert plain.profit == Decimal("157650.00")

    shown = _render(True)
    shown_policies = next(note for note in shown.notes if note.code == "N1_POLICIES")
    shown_stocks = next(row for row in shown.sofp if row.label == "Stocks")
    assert (
        f"The carrying amount of stocks is {format_whole(shown_stocks.current)}."
        in shown_policies.body
    )
    assert shown_stocks.prior is not None
    assert format_whole(shown_stocks.prior) in shown_policies.body
    assert "1AD" not in shown_policies.body
    assert "optional for a small entity" not in shown_policies.body
    assert shown.net_assets == Decimal("455812.00")
    assert shown.profit == Decimal("157650.00")
