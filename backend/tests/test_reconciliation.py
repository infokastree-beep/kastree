"""Week 6 and Week 7 reconciliation checks."""

from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal
from app.main import app
from app.services.fa_import_worker import process_fa_version
from app.services.reconciliation import (
    ReconciliationReport,
    build_reconciliation,
    statutory_lines,
)
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from app.services.tb_import_worker import process_tb_version
from findraft.engine.schemas import TBLine
from tests.conftest import auth_headers, make_access_token
from tests.test_organisations_api import _add_org_user
from tests.test_role_enforcement import _set_role
from tests.test_fa_ingestion import _csv_bytes
from tests.test_tb_ingestion import _upload, _year_end

_FORBIDDEN = "You don't have permission to access this resource."
_BANK = "V-BANK-001"
_CORE = ("V-TB-001", "V-MAP-001", "V-BS-001", "V-FA-001", "V-RE-001")

# Copied from the golden fixture. That module imports engine.* and is not a package.
_TB: tuple[tuple[str, str, int, int], ...] = (
    ("1500", "Plant & machinery - cost", 150000, 0),
    ("1501", "Motor vehicles - cost", 60000, 0),
    ("1505", "Accumulated depreciation - plant", 0, 52000),
    ("1506", "Accumulated depreciation - motor", 0, 24000),
    ("2100", "Trade debtors", 245800, 0),
    ("2110", "Other debtors", 15400, 0),
    ("2120", "Prepayments", 6200, 0),
    ("2130", "Bank current account", 284912, 0),
    ("2200", "Trade creditors", 0, 67200),
    ("2210", "Other creditors", 0, 8400),
    ("2220", "Accruals", 0, 5600),
    ("2230", "Corporation tax", 0, 14300),
    ("2240", "Loan - due within one year", 0, 15000),
    ("2300", "Loan - due after more than one year", 0, 120000),
    ("3000", "Called up share capital", 0, 100),
    ("3100", "Retained earnings b/f", 0, 322062),
    ("4000", "Sales revenue", 0, 2421300),
    ("5000", "Cost of sales", 1579600, 0),
    ("6000", "Administrative expenses", 611750, 0),
    ("6100", "Interest receivable", 0, 1200),
    ("7000", "Depreciation charge", 22400, 0),
    ("7100", "Interest payable", 9600, 0),
    ("8500", "Dividends paid", 24000, 0),
    ("8600", "Tax charge", 41500, 0),
)
_MAPPINGS = {
    "1500": "FA_PLANT_COST",
    "1501": "FA_MOTOR_COST",
    "1505": "FA_ACCUM_DEP",
    "1506": "FA_ACCUM_DEP",
    "2100": "TRADE_DEBTORS",
    "2110": "OTHER_DEBTORS",
    "2120": "PREPAYMENTS",
    "2130": "CASH",
    "2200": "TRADE_CREDITORS",
    "2210": "OTHER_CREDITORS",
    "2220": "ACCRUALS",
    "2230": "CORP_TAX",
    "2240": "LOANS_LT1Y",
    "2300": "LOANS_GT1Y",
    "3000": "SHARE_CAPITAL",
    "3100": "RETAINED_EARNINGS",
    "4000": "REVENUE",
    "5000": "COST_OF_SALES",
    "6000": "ADMIN_EXPENSES",
    "6100": "INTEREST_RECEIVABLE",
    "7000": "DEPRECIATION_CHARGE",
    "7100": "INTEREST_PAYABLE",
    "8500": "DIVIDENDS",
    "8600": "TAX_CHARGE",
}
_TINY = (
    "Account Code,Account Name,Debit,Credit\n"
    "1200,Bank current account,100.00,0.00\n"
    "3000,Called up share capital,0.00,100.00\n"
)


@pytest.fixture
def stored_files(tmp_path: Path) -> Iterator[LocalPracticeStorage]:
    store = LocalPracticeStorage(tmp_path)
    app.dependency_overrides[get_source_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_source_storage, None)


def _lines(rows: tuple[tuple[str, str, int, int], ...]) -> list[TBLine]:
    return [
        TBLine(code, name, Decimal(str(debit)), Decimal(str(credit)))
        for code, name, debit, credit in rows
    ]


def _golden_csv() -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Account Code", "Account Name", "Debit", "Credit"])
    for code, name, debit, credit in _TB:
        writer.writerow([code, name, f"{debit:.2f}", f"{credit:.2f}"])
    return buffer.getvalue().encode()


def _mapping_payload(mappings: dict[str, str]) -> dict[str, list[dict[str, str]]]:
    return {
        "lines": [
            {"nominal_code": code, "canonical_line": line}
            for code, line in mappings.items()
        ]
    }


def _passed(body: dict[str, object]) -> list[tuple[str, bool]]:
    checks = body["checks"]
    assert isinstance(checks, list)
    return [(str(item["code"]), bool(item["passed"])) for item in checks]


def _report_pairs(report: ReconciliationReport) -> list[tuple[str, bool]]:
    return [(item.code, item.passed) for item in report.checks]


def _assert_statement_checks(
    pairs: list[tuple[str, bool]], *, fa_passed: bool = True
) -> None:
    core = [(code, passed) for code, passed in pairs if code in _CORE]
    assert core == [
        ("V-TB-001", True),
        ("V-MAP-001", True),
        ("V-BS-001", True),
        ("V-FA-001", fa_passed),
        ("V-RE-001", True),
    ]
    comparative = [passed for code, passed in pairs if code == "V-CMP-001"]
    assert comparative
    assert all(comparative)
    assert all(code != "V-CMP-002" for code, _ok in pairs)
    assert all(code != _BANK for code, _ok in pairs)


async def _import_csv(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
    *,
    year_end_id: str,
    name: str,
    content: bytes,
    file_key: str,
    version_key: str,
    process: bool,
) -> str:
    document_id = await _upload(
        api_client,
        provisioned_org,
        name=name,
        content=content,
        key=file_key,
        content_type="text/csv",
    )
    headers = auth_headers(provisioned_org["token"])
    headers["Idempotency-Key"] = version_key
    created = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions",
        headers=headers,
        json={"source_document_id": document_id},
    )
    assert created.status_code == 202, created.text
    version_id = str(created.json()["id"])
    assert created.json()["status"] == "pending"
    if process:
        with SyncSessionLocal() as session:
            processed = process_tb_version(
                session,
                org_id=provisioned_org["org_id"],
                version_id=uuid.UUID(version_id),
                storage=stored_files,
            )
            assert processed is not None
            assert processed.status == "ready"
    return version_id


def test_statutory_lines_include_sign_homes_and_refuse_loans() -> None:
    allowed = statutory_lines()
    assert "DIRECTOR_LOAN" in allowed
    assert "BANK_OVERDRAFT" in allowed
    assert "CASH" in allowed
    assert "LOANS" not in allowed


_FA_REGISTER = {
    "Plant & machinery": {
        "opening_cost": Decimal("120000"),
        "additions": Decimal("30000"),
        "disposals": Decimal("0"),
        "opening_dep": Decimal("35600"),
        "charge": Decimal("16400"),
    },
    "Motor vehicles": {
        "opening_cost": Decimal("45000"),
        "additions": Decimal("15000"),
        "disposals": Decimal("0"),
        "opening_dep": Decimal("18000"),
        "charge": Decimal("6000"),
    },
}


def test_golden_fixture_reconciles() -> None:
    from findraft.engine.reconciliation import check_fa_rollforward

    report = build_reconciliation(
        prior_year_validated=True,
        tb_lines=_lines(_TB),
        mappings=_MAPPINGS,
        prior_retained_earnings=Decimal("-322062.00"),
        prior_canonical={
            "FA_PLANT_COST": Decimal("111400.00"),
            "RETAINED_EARNINGS": Decimal("-322062.00"),
        },
        fa_register=_FA_REGISTER,
    )
    assert report.blocked is False
    assert report.build_error is None
    _assert_statement_checks(_report_pairs(report))
    assert report.net_assets == Decimal("455812.00")
    assert report.profit == Decimal("157650.00")
    engine_fa = check_fa_rollforward(
        Decimal("111400"),
        Decimal("45000"),
        Decimal("22400"),
        Decimal("0"),
        Decimal("134000"),
    )
    fa = next(item for item in report.checks if item.code == "V-FA-001")
    assert fa.passed is True
    assert fa.message == engine_fa.message
    tangible = next(
        item
        for item in report.checks
        if item.code == "V-CMP-001" and "Comparative TANGIBLE_ASSETS:" in item.message
    )
    assert tangible.passed is True
    assert "111400" in tangible.message.replace(",", "")
    assert all(not item.code.startswith("R-") for item in report.checks)


def test_unbalanced_tb_fails_integrity() -> None:
    rows = (
        ("1200", "Bank current account", 100, 0),
        ("3000", "Called up share capital", 0, 50),
    )
    report = build_reconciliation(
        prior_year_validated=True,
        tb_lines=_lines(rows),
        mappings={"1200": "CASH", "3000": "SHARE_CAPITAL"},
        prior_retained_earnings=Decimal("0.00"),
    )
    assert report.blocked is False
    assert report.checks[0].code == "V-TB-001"
    assert report.checks[0].passed is False
    assert "V-BS-001" in {item.code for item in report.checks}


def test_loans_is_a_build_error() -> None:
    rows = (
        ("2300", "Loan", 0, 50),
        ("3000", "Called up share capital", 50, 0),
    )
    report = build_reconciliation(
        prior_year_validated=True,
        tb_lines=_lines(rows),
        mappings={"2300": "LOANS", "3000": "SHARE_CAPITAL"},
        prior_retained_earnings=Decimal("0.00"),
    )
    assert report.build_error is not None
    assert "LOANS" in report.build_error
    assert report.net_assets is None
    assert report.profit is None
    assert "V-BS-001" not in {item.code for item in report.checks}
    assert "V-RE-001" not in {item.code for item in report.checks}
    assert "V-FA-001" not in {item.code for item in report.checks}
    assert _BANK not in {item.code for item in report.checks}


def test_director_loan_sign_home_reaches_the_statements() -> None:
    rows = (
        ("2100", "Director loan", 50, 0),
        ("3000", "Called up share capital", 0, 50),
    )
    report = build_reconciliation(
        prior_year_validated=True,
        tb_lines=_lines(rows),
        mappings={"2100": "DIRECTOR_LOAN", "3000": "SHARE_CAPITAL"},
        prior_retained_earnings=Decimal("0.00"),
    )
    assert report.build_error is None
    _assert_statement_checks(_report_pairs(report))
    assert report.net_assets == Decimal("50.00")
    assert report.profit == Decimal("0.00")
    assert all(not item.code.startswith("R-") for item in report.checks)


def test_closed_gate_stops_later_checks() -> None:
    report = build_reconciliation(
        prior_year_validated=False,
        tb_lines=_lines(_TB),
        mappings=_MAPPINGS,
        prior_retained_earnings=Decimal("-322062.00"),
    )
    assert report.blocked is True
    assert report.build_error is None
    assert [(item.code, item.passed) for item in report.checks] == [
        ("V-GATE-001", False),
    ]
    assert report.net_assets is None
    assert report.profit is None


def test_disposal_register_rolls_net_book_value_forward() -> None:
    rows = (
        ("2130", "Bank current account", 100, 0),
        ("3000", "Called up share capital", 0, 100),
    )
    report = build_reconciliation(
        prior_year_validated=True,
        tb_lines=_lines(rows),
        mappings={"2130": "CASH", "3000": "SHARE_CAPITAL"},
        prior_retained_earnings=Decimal("0.00"),
        fa_register={
            "Plant": {
                "opening_cost": Decimal("100000"),
                "additions": Decimal("0"),
                "disposals": Decimal("20000"),
                "disposals_dep": Decimal("5000"),
                "opening_dep": Decimal("10000"),
                "charge": Decimal("4000"),
            }
        },
    )
    fa = next(item for item in report.checks if item.code == "V-FA-001")
    assert fa.passed is True
    assert "71,000" in fa.message


def test_missing_register_fails_when_the_face_shows_fixed_assets() -> None:
    rows = (
        ("1500", "Plant", 100, 0),
        ("3000", "Called up share capital", 0, 100),
    )
    report = build_reconciliation(
        prior_year_validated=True,
        tb_lines=_lines(rows),
        mappings={"1500": "FA_PLANT_COST", "3000": "SHARE_CAPITAL"},
        prior_retained_earnings=Decimal("0.00"),
    )
    _assert_statement_checks(_report_pairs(report), fa_passed=False)
    dep = next(item for item in report.checks if item.code == "R-DEP-001")
    assert dep.passed is False
    assert dep.severity == "WARNING"


def test_dividends_above_accumulated_profits_are_critical() -> None:
    rows = (
        ("2130", "Bank", 20, 0),
        ("8500", "Dividends", 80, 0),
        ("3000", "Share capital", 0, 100),
    )
    report = build_reconciliation(
        prior_year_validated=True,
        tb_lines=_lines(rows),
        mappings={
            "2130": "CASH",
            "8500": "DIVIDENDS",
            "3000": "SHARE_CAPITAL",
        },
        prior_retained_earnings=Decimal("0.00"),
    )
    dividend = next(item for item in report.checks if item.code == "R-DIV-001")
    assert dividend.passed is False
    assert dividend.severity == "CRITICAL"
    assert _BANK not in {item.code for item in report.checks}


def test_unevaluable_pack_rule_stays_critical(tmp_path: Path) -> None:
    rules = tmp_path / "review-rules.json"
    rules.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "R-BROKEN-001",
                        "scope": "client",
                        "severity": "WARNING",
                        "when": "not_a_real_input > 0",
                        "message": "should not pass",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rows = (
        ("2130", "Bank", 100, 0),
        ("3000", "Share capital", 0, 100),
    )
    report = build_reconciliation(
        prior_year_validated=True,
        tb_lines=_lines(rows),
        mappings={"2130": "CASH", "3000": "SHARE_CAPITAL"},
        prior_retained_earnings=Decimal("0.00"),
        pack_rules_path=rules,
    )
    broken = next(item for item in report.checks if item.code == "R-BROKEN-001")
    assert broken.passed is False
    assert broken.severity == "CRITICAL"
    assert report.build_error is None
    assert "could not be evaluated" in broken.message


@pytest.mark.asyncio
async def test_golden_upload_confirms_and_reconciles(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    headers = auth_headers(provisioned_org["token"])
    version_id = await _import_csv(
        api_client,
        provisioned_org,
        stored_files,
        year_end_id=year_end_id,
        name="golden.csv",
        content=_golden_csv(),
        file_key="golden-file",
        version_key="golden-version",
        process=True,
    )
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
        key="golden-fa-file",
        content_type="text/csv",
    )
    fa_headers = auth_headers(provisioned_org["token"])
    fa_headers["Idempotency-Key"] = "golden-fa-version"
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
    confirmed = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json=_mapping_payload(_MAPPINGS),
    )
    assert confirmed.status_code == 200, confirmed.text
    assert len(confirmed.json()["lines"]) == len(_MAPPINGS)
    report = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/reconciliation",
        headers=headers,
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["blocked"] is False
    assert body["build_error"] is None
    _assert_statement_checks(_passed(body))
    assert body["net_assets"] == "455812.00"
    assert body["profit"] == "157650.00"
    assert all(not code.startswith("R-") for code, _ok in _passed(body))
    tangible = next(
        item
        for item in body["checks"]
        if item["code"] == "V-CMP-001"
        and "Comparative TANGIBLE_ASSETS:" in item["message"]
    )
    assert tangible["passed"] is True
    assert "111400" in tangible["message"].replace(",", "")


@pytest.mark.asyncio
async def test_closed_gate_blocks_before_readiness(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    headers = auth_headers(provisioned_org["token"])
    version_id = await _import_csv(
        api_client,
        provisioned_org,
        stored_files,
        year_end_id=year_end_id,
        name="tiny.csv",
        content=_TINY.encode(),
        file_key="gate-file",
        version_key="gate-version",
        process=False,
    )
    blocked = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/reconciliation",
        headers=headers,
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["blocked"] is True
    assert [item["code"] for item in blocked.json()["checks"]] == ["V-GATE-001"]
    assert blocked.json()["net_assets"] is None
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json=_mapping_payload({"1200": "CASH", "3000": "SHARE_CAPITAL"}),
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"] == "Trial balance version is not ready"
    opened = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert opened.status_code == 200, opened.text
    still_pending = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/reconciliation",
        headers=headers,
    )
    assert still_pending.status_code == 400, still_pending.text
    assert still_pending.json()["detail"] == "Trial balance version is not ready"


@pytest.mark.asyncio
async def test_unmapped_ready_version_stops_before_the_balance_sheet(
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
        name="tiny.csv",
        content=_TINY.encode(),
        file_key="unmap-file",
        version_key="unmap-version",
        process=True,
    )
    report = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/reconciliation",
        headers=headers,
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["blocked"] is False
    assert _passed(body) == [("V-TB-001", True), ("V-MAP-001", False)]
    assert body["net_assets"] is None
    assert body["profit"] is None
    assert body["build_error"] is None


@pytest.mark.asyncio
async def test_first_period_tiny_trial_balance_articulates(
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
        name="tiny.csv",
        content=_TINY.encode(),
        file_key="tiny-file",
        version_key="tiny-version",
        process=True,
    )
    confirmed = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json=_mapping_payload({"1200": "CASH", "3000": "SHARE_CAPITAL"}),
    )
    assert confirmed.status_code == 200, confirmed.text
    report = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/reconciliation",
        headers=headers,
    )
    assert report.status_code == 200, report.text
    body = report.json()
    _assert_statement_checks(_passed(body))
    assert all(not code.startswith("R-") for code, _ok in _passed(body))
    assert body["net_assets"] == "100.00"
    assert body["profit"] == "0.00"


@pytest.mark.asyncio
async def test_fixed_assets_without_a_register_fail_the_roll_forward(
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
        file_key="plant-file",
        version_key="plant-version",
        process=True,
    )
    confirmed = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json=_mapping_payload({"1500": "FA_PLANT_COST", "3000": "SHARE_CAPITAL"}),
    )
    assert confirmed.status_code == 200, confirmed.text
    report = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/reconciliation",
        headers=headers,
    )
    assert report.status_code == 200, report.text
    body = report.json()
    _assert_statement_checks(_passed(body), fa_passed=False)
    dep = next(item for item in body["checks"] if item["code"] == "R-DEP-001")
    assert dep["passed"] is False
    assert dep["severity"] == "WARNING"
    assert _BANK not in {item["code"] for item in body["checks"]}


@pytest.mark.asyncio
async def test_confirm_rejects_bad_mappings_and_a_second_write(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    headers = auth_headers(provisioned_org["token"])
    version_id = await _import_csv(
        api_client,
        provisioned_org,
        stored_files,
        year_end_id=year_end_id,
        name="tiny.csv",
        content=_TINY.encode(),
        file_key="reject-file",
        version_key="reject-version",
        process=True,
    )
    loans = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json=_mapping_payload({"1200": "LOANS", "3000": "SHARE_CAPITAL"}),
    )
    assert loans.status_code == 400, loans.text
    assert loans.json()["detail"] == "Unknown canonical line: LOANS"
    partial = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json=_mapping_payload({"1200": "CASH"}),
    )
    assert partial.status_code == 400, partial.text
    assert "3000" in partial.json()["detail"]
    unknown = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json=_mapping_payload(
            {"1200": "CASH", "3000": "SHARE_CAPITAL", "9999": "CASH"}
        ),
    )
    assert unknown.status_code == 400, unknown.text
    assert unknown.json()["detail"] == "Unknown nominal code: 9999"
    duplicate = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json={
            "lines": [
                {"nominal_code": "1200", "canonical_line": "CASH"},
                {"nominal_code": "1200", "canonical_line": "CASH"},
                {"nominal_code": "3000", "canonical_line": "SHARE_CAPITAL"},
            ]
        },
    )
    assert duplicate.status_code == 400, duplicate.text
    assert duplicate.json()["detail"] == "Duplicate nominal code: 1200"
    with SyncSessionLocal() as session:
        stored = session.execute(
            text(
                """
                SELECT count(*) FROM findraft_confirmed_mappings
                WHERE tb_version_id = :id
                """
            ),
            {"id": version_id},
        ).scalar_one()
        assert stored == 0
    confirmed = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json=_mapping_payload({"1200": "CASH", "3000": "SHARE_CAPITAL"}),
    )
    assert confirmed.status_code == 200, confirmed.text
    again = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json=_mapping_payload({"1200": "CASH", "3000": "SHARE_CAPITAL"}),
    )
    assert again.status_code == 409, again.text
    assert again.json()["detail"] == "Mappings are already confirmed"


@pytest.mark.asyncio
async def test_viewer_can_read_reconciliation_and_cannot_confirm(
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
        file_key="viewer-file",
        version_key="viewer-version",
        process=False,
    )
    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="recon-viewer",
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
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/reconciliation",
        headers=viewer,
    )
    assert readable.status_code == 200, readable.text
    assert readable.json()["blocked"] is True
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=viewer,
        json=_mapping_payload({"1200": "CASH", "3000": "SHARE_CAPITAL"}),
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"] == _FORBIDDEN


@pytest.mark.asyncio
async def test_unknown_year_end_or_version_is_not_found(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    missing = await api_client.get(
        f"/year-ends/{uuid.uuid4()}/trial-balance-versions/{uuid.uuid4()}/reconciliation",
        headers=headers,
    )
    assert missing.status_code == 404, missing.text
    first = await _year_end(api_client, provisioned_org)
    version_id = await _import_csv(
        api_client,
        provisioned_org,
        stored_files,
        year_end_id=first,
        name="tiny.csv",
        content=_TINY.encode(),
        file_key="other-file",
        version_key="other-version",
        process=False,
    )
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
        f"/year-ends/{second.json()['id']}/trial-balance-versions/{version_id}/reconciliation",
        headers=headers,
    )
    assert other.status_code == 404, other.text
