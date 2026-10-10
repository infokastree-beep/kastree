"""Adopt a completed Product 1 trial balance into a statutory year end.

The year end stores trial_balances.id. No findraft_tb_versions row is
created, and account_mappings are not copied into findraft_confirmed_mappings.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
import zipfile
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import SyncSessionLocal, set_rls_org_id
from app.main import app
from app.models.account_mapping import AccountMapping
from app.models.company import Company
from app.models.trial_balance import TrialBalance
from app.services.adopted_trial_balance import (
    ConfirmedAccount,
    SourceAccount,
    carry_confirmed_accounts,
    engine_line_for_confirmed_mapping,
)
from app.services.fa_import_worker import process_fa_version
from app.services.reconciliation import ReconciliationRejected
from app.services.render_jobs import process_render_job
from findraft.engine.notes import ANSWER_FLAGS
from findraft.models.adjustments import DisclosureAnswer
from app.services.statutory_sublines import needs_statutory_subline, suggest_subline
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from tests.conftest import auth_headers, make_access_token
from tests.test_fa_ingestion import _csv_bytes
from tests.test_findraft_tenant_isolation import _as_app_role, _delete_org, _provision
from tests.test_organisations_api import _add_org_user
from tests.test_reconciliation import _MAPPINGS, _TB
from tests.test_role_enforcement import _set_role
from tests.test_tb_ingestion import _upload, _year_end

_FORBIDDEN = "You don't have permission to access this resource."
_PRODUCT1 = {
    "1500": "property_plant_equipment",
    "1501": "property_plant_equipment",
    "1505": "property_plant_equipment",
    "1506": "property_plant_equipment",
    "2100": "trade_receivables",
    "2110": "other_receivables",
    "2120": "prepayments",
    "2130": "cash",
    "2200": "trade_payables",
    "2210": "other_payables",
    "2220": "accruals",
    "2230": "taxes_payable",
    "2240": "loans",
    "2300": "loans",
    "3000": "share_capital",
    "3100": "retained_earnings",
    "4000": "revenue",
    "5000": "cost_of_sales",
    "6000": "operating_expenses",
    "6100": "interest_income",
    "7000": "depreciation",
    "7100": "interest_expense",
    "8500": "dividends",
    "8600": "tax",
}


@pytest.fixture
def stored_files(tmp_path: Path) -> Iterator[LocalPracticeStorage]:
    store = LocalPracticeStorage(tmp_path)
    app.dependency_overrides[get_source_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_source_storage, None)


def test_golden_chart_translates_once_the_subline_is_confirmed() -> None:
    carried: dict[str, str] = {}
    for code, name, _debit, _credit in _TB:
        product1 = _PRODUCT1[code]
        if needs_statutory_subline(product1):
            hit = suggest_subline(product1, name)
            assert hit is not None
            assert hit.engine_line == _MAPPINGS[code]
            with pytest.raises(
                ReconciliationRejected, match="needs a statutory sub-line"
            ):
                engine_line_for_confirmed_mapping(product1, name)
            carried[code] = engine_line_for_confirmed_mapping(
                product1, name, hit.engine_line
            )
        else:
            carried[code] = engine_line_for_confirmed_mapping(product1, name)
    assert carried == _MAPPINGS


def test_coarse_lines_without_one_statutory_home_are_refused() -> None:
    refused = (
        ("gross_profit", "Sales revenue"),
        ("unmapped", "Sundry"),
    )
    for product1_line, account_name in refused:
        with pytest.raises(ReconciliationRejected, match="no single statutory line"):
            engine_line_for_confirmed_mapping(product1_line, account_name)
    needs_choice = (
        ("loans", "Bank loan"),
        ("operating_expenses", "Rent"),
        ("amortisation", "Amortisation charge"),
        ("property_plant_equipment", "Sundry asset"),
    )
    for product1_line, account_name in needs_choice:
        with pytest.raises(ReconciliationRejected, match="needs a statutory sub-line"):
            engine_line_for_confirmed_mapping(product1_line, account_name)


def test_carry_refuses_an_unconfirmed_account_and_a_duplicate_code() -> None:
    accounts = (
        SourceAccount("1000", "Bank", Decimal("10"), Decimal("0"), 0),
        SourceAccount("3000", "Capital", Decimal("0"), Decimal("10"), 1),
    )
    with pytest.raises(ReconciliationRejected, match="is not confirmed"):
        carry_confirmed_accounts(
            accounts,
            {
                ("1000", "Bank"): ConfirmedAccount("cash", True, False),
            },
        )
    with pytest.raises(ReconciliationRejected, match="Duplicate nominal code"):
        carry_confirmed_accounts(
            (
                SourceAccount("1000", "Bank", Decimal("10"), Decimal("0"), 0),
                SourceAccount("1000", "Bank again", Decimal("0"), Decimal("10"), 1),
            ),
            {
                ("1000", "Bank"): ConfirmedAccount("cash", True, False),
                ("1000", "Bank again"): ConfirmedAccount("cash", True, False),
            },
        )


def _parsed_rows(
    rows: tuple[tuple[str, str, str, str, str], ...],
) -> dict[str, list[dict[str, str | int]]]:
    return {
        "rows": [
            {
                "account_code": code,
                "account_name": name,
                "debit": debit,
                "credit": credit,
                "net_balance": net,
                "currency": "EUR",
                "row_index": index,
            }
            for index, (code, name, debit, credit, net) in enumerate(rows)
        ]
    }


def _insert_tb(
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    rows: tuple[tuple[str, str, str, str, str, str], ...],
    status: str = "complete",
    period_end: date = date(2026, 12, 31),
    period_start: date | None = None,
    confirmed: bool = True,
    confirm_sublines: bool = True,
) -> uuid.UUID:
    tb_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            TrialBalance(
                id=tb_id,
                company_id=company_id,
                period_end=period_end,
                period_start=period_start,
                file_url=f"file:///tmp/{tb_id}.csv",
                file_type="csv",
                status=status,
                currency="EUR",
                parsed_data=_parsed_rows(
                    tuple(
                        (code, name, debit, credit, net)
                        for code, name, debit, credit, net, _line in rows
                    )
                ),
            )
        )
        for code, name, _debit, _credit, _net, line in rows:
            statutory_line = None
            if confirm_sublines:
                if needs_statutory_subline(line):
                    hit = suggest_subline(line, name)
                    if hit is not None:
                        statutory_line = hit.engine_line
            session.add(
                AccountMapping(
                    company_id=company_id,
                    source_code=code,
                    source_name=name,
                    canonical_line=line,
                    confidence=Decimal("1.00"),
                    method="manual",
                    is_confirmed=confirmed,
                    is_ignored=False,
                    statutory_line=statutory_line,
                )
            )
        session.commit()
    return tb_id


def _golden_rows() -> tuple[tuple[str, str, str, str, str, str], ...]:
    built: list[tuple[str, str, str, str, str, str]] = []
    for code, name, debit, credit in _TB:
        net = Decimal(debit) - Decimal(credit)
        built.append(
            (
                code,
                name,
                f"{debit:.2f}",
                f"{credit:.2f}",
                f"{net:.2f}",
                _PRODUCT1[code],
            )
        )
    return tuple(built)


def _retire(tb_id: uuid.UUID, org_id: uuid.UUID) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                "UPDATE trial_balances "
                "SET is_deleted = true, deleted_at = NOW() WHERE id = :id"
            ),
            {"id": str(tb_id)},
        )
        session.commit()


def _pointer(year_end_id: str, org_id: uuid.UUID) -> str | None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        value = session.execute(
            text(
                "SELECT adopted_trial_balance_id FROM findraft_year_ends "
                "WHERE id = :id"
            ),
            {"id": year_end_id},
        ).scalar_one()
    if value is None:
        return None
    return str(value)


def _draft_count(year_end_id: str, org_id: uuid.UUID) -> int:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        count = session.execute(
            text(
                "SELECT count(*) FROM findraft_draft_versions "
                "WHERE year_end_id = :id"
            ),
            {"id": year_end_id},
        ).scalar_one()
    return int(count)


def _child_count(table: str, draft_id: str, org_id: uuid.UUID) -> int:
    if table == "findraft_adjustment_journals":
        statement = (
            "SELECT count(*) FROM findraft_adjustment_journals "
            "WHERE draft_version_id = :id"
        )
    elif table == "findraft_disclosure_answers":
        statement = (
            "SELECT count(*) FROM findraft_disclosure_answers "
            "WHERE draft_version_id = :id"
        )
    else:
        raise AssertionError(table)
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        count = session.execute(text(statement), {"id": draft_id}).scalar_one()
    return int(count)


def _frozen_mapping(
    draft_id: str, nominal_code: str, org_id: uuid.UUID
) -> str | None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        value = session.execute(
            text(
                "SELECT frozen_inputs->'mappings'->>:code "
                "FROM findraft_draft_versions WHERE id = :id"
            ),
            {"code": nominal_code, "id": draft_id},
        ).scalar_one()
    if value is None:
        return None
    return str(value)


def _remap(
    company_id: uuid.UUID,
    source_code: str,
    canonical_line: str,
    org_id: uuid.UUID,
) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                "UPDATE account_mappings SET canonical_line = :line "
                "WHERE company_id = :company AND source_code = :code"
            ),
            {
                "line": canonical_line,
                "company": str(company_id),
                "code": source_code,
            },
        )
        session.commit()


def _sofp_amount(body: dict[str, object], label: str) -> str:
    rows = body["sofp"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        if row["label"] == label:
            return str(row["current"])
    raise AssertionError(label)


def _statutory_copy_counts(org_id: uuid.UUID, year_end_id: str) -> tuple[int, int]:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        versions = session.execute(
            text("SELECT count(*) FROM findraft_tb_versions WHERE year_end_id = :id"),
            {"id": year_end_id},
        ).scalar_one()
        mappings = session.execute(
            text(
                "SELECT count(*) FROM findraft_confirmed_mappings WHERE org_id = :oid"
            ),
            {"oid": str(org_id)},
        ).scalar_one()
    return int(versions), int(mappings)


@pytest.mark.asyncio
async def test_adopted_golden_keeps_engine_figures_without_a_statutory_copy(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    tb_id = _insert_tb(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        rows=_golden_rows(),
    )
    headers = auth_headers(provisioned_org["token"])
    listed = await api_client.get(
        f"/year-ends/{year_end_id}/adoptable-trial-balances",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [str(tb_id)]
    assert listed.json()["items"][0]["account_count"] == len(_TB)

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
        key="adopt-fa-file",
        content_type="text/csv",
    )
    fa_headers = auth_headers(provisioned_org["token"])
    fa_headers["Idempotency-Key"] = "adopt-fa-version"
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
        session.commit()

    adopted = await api_client.post(
        f"/year-ends/{year_end_id}/adopt-trial-balance",
        headers=headers,
        json={"trial_balance_id": str(tb_id)},
    )
    assert adopted.status_code == 200, adopted.text
    body = adopted.json()
    assert body["trial_balance_id"] == str(tb_id)
    assert {
        line["nominal_code"]: line["canonical_line"] for line in body["lines"]
    } == _MAPPINGS
    assert _pointer(year_end_id, provisioned_org["org_id"]) == str(tb_id)
    assert _statutory_copy_counts(provisioned_org["org_id"], year_end_id) == (0, 0)

    statements = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert statements.status_code == 200, statements.text
    assert statements.json()["net_assets"] == "455812.00"
    assert statements.json()["profit"] == "157650.00"
    assert statements.json()["renderable"] is True
    reconciliation = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/reconciliation",
        headers=headers,
    )
    assert reconciliation.status_code == 200, reconciliation.text
    assert reconciliation.json()["net_assets"] == "455812.00"
    assert reconciliation.json()["profit"] == "157650.00"
    anonymous = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
    )
    assert anonymous.status_code == 401, anonymous.text
    pdf = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
        headers=headers,
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert (
        pdf.headers["content-disposition"]
        == 'attachment; filename="statutory-statements-draft.pdf"'
    )
    assert pdf.content.startswith(b"%PDF")
    assert _statutory_copy_counts(provisioned_org["org_id"], year_end_id) == (0, 0)


@pytest.mark.asyncio
async def test_adopt_refuses_incomplete_unconfirmed_and_other_company(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    headers = auth_headers(provisioned_org["token"])
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    other_period = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(
            ("2132", "Petty cash", "5.00", "0.00", "5.00", "cash"),
            ("3003", "Founder shares", "0.00", "5.00", "-5.00", "share_capital"),
        ),
        period_end=date(2026, 6, 30),
    )
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        other = Company(
            client_id=provisioned_org["client_id"],
            name="Other company",
            functional_currency="EUR",
        )
        session.add(other)
        session.commit()
        other_company_id = other.id
    other_tb = _insert_tb(
        org_id=org_id,
        company_id=other_company_id,
        rows=(
            ("2133", "Client account", "8.00", "0.00", "8.00", "cash"),
            ("3004", "Subscriber capital", "0.00", "8.00", "-8.00", "share_capital"),
        ),
    )

    same_period = (
        (
            (
                ("2130", "Bank current account", "100.00", "0.00", "100.00", "cash"),
                (
                    "3000",
                    "Called up share capital",
                    "0.00",
                    "100.00",
                    "-100.00",
                    "share_capital",
                ),
            ),
            {"status": "mapping", "confirmed": True},
        ),
        (
            (
                ("2131", "Deposit account", "40.00", "0.00", "40.00", "cash"),
                ("3001", "Ordinary shares", "0.00", "40.00", "-40.00", "share_capital"),
            ),
            {"status": "complete", "confirmed": False},
        ),
    )
    for rows, options in same_period:
        tb_id = _insert_tb(
            org_id=org_id,
            company_id=company_id,
            rows=rows,
            status=str(options["status"]),
            confirmed=bool(options["confirmed"]),
        )
        listed = await api_client.get(
            f"/year-ends/{year_end_id}/adoptable-trial-balances",
            headers=headers,
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()["items"] == []
        response = await api_client.post(
            f"/year-ends/{year_end_id}/adopt-trial-balance",
            headers=headers,
            json={"trial_balance_id": str(tb_id)},
        )
        assert response.status_code == 400, response.text
        assert _pointer(year_end_id, org_id) is None
        _retire(tb_id, org_id)

    # A confirmed chart that still needs a sub-line can be adopted. The
    # draft opens; statement generation stays closed until the choice.
    waiting = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(
            ("6100", "Rent", "25.00", "0.00", "25.00", "operating_expenses"),
            (
                "3002",
                "Capital introduced",
                "0.00",
                "25.00",
                "-25.00",
                "share_capital",
            ),
        ),
        confirm_sublines=False,
    )
    listed = await api_client.get(
        f"/year-ends/{year_end_id}/adoptable-trial-balances",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [str(waiting)]
    _retire(waiting, org_id)
    cleared = await api_client.get(
        f"/year-ends/{year_end_id}/adoptable-trial-balances",
        headers=headers,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["items"] == []

    for tb_id, status in ((other_period, 400), (other_tb, 404), (uuid.uuid4(), 404)):
        response = await api_client.post(
            f"/year-ends/{year_end_id}/adopt-trial-balance",
            headers=headers,
            json={"trial_balance_id": str(tb_id)},
        )
        assert response.status_code == status, response.text
        assert _pointer(year_end_id, org_id) is None


@pytest.mark.asyncio
async def test_viewer_can_read_adoption_and_cannot_adopt(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    tb_id = _insert_tb(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        rows=(
            ("2130", "Bank current account", "100.00", "0.00", "100.00", "cash"),
            (
                "3000",
                "Called up share capital",
                "0.00",
                "100.00",
                "-100.00",
                "share_capital",
            ),
        ),
    )
    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="adopt-role",
    )
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="owner",
        org_uuid=provisioned_org["org_id"],
    )
    headers = auth_headers(token)
    adopted = await api_client.post(
        f"/year-ends/{year_end_id}/adopt-trial-balance",
        headers=headers,
        json={"trial_balance_id": str(tb_id)},
    )
    assert adopted.status_code == 200, adopted.text
    _set_role(org_id=provisioned_org["org_id"], user_id=user_id, role="viewer")
    forbidden = await api_client.post(
        f"/year-ends/{year_end_id}/adopt-trial-balance",
        headers=headers,
        json={"trial_balance_id": str(tb_id)},
    )
    assert forbidden.status_code == 403, forbidden.text
    assert forbidden.json()["detail"] == _FORBIDDEN
    statements = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert statements.status_code == 200, statements.text
    assert statements.json()["renderable"] is False
    listed = await api_client.get(
        f"/year-ends/{year_end_id}/adoptable-trial-balances",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"][0]["id"] == str(tb_id)


def _insert_bare_tb(company_id: uuid.UUID, org_id: uuid.UUID) -> uuid.UUID:
    tb_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                """
                INSERT INTO trial_balances (
                  id, company_id, period_end, file_url, file_type, status, currency
                ) VALUES (
                  :id, :company, DATE '2026-12-31', :url, 'csv', 'complete', 'EUR'
                )
                """
            ),
            {
                "id": str(tb_id),
                "company": str(company_id),
                "url": f"file:///tmp/{tb_id}.csv",
            },
        )
        session.commit()
    return tb_id


def test_findraft_app_cannot_adopt_another_practices_trial_balance() -> None:
    suffix = uuid.uuid4().hex[:8]
    first = _provision(f"a{suffix}")
    second = _provision(f"b{suffix}")
    first_tb = _insert_bare_tb(first["company_id"], first["org_id"])
    second_tb = _insert_bare_tb(second["company_id"], second["org_id"])
    try:
        with SyncSessionLocal() as session:
            try:
                _as_app_role(session)
                session.execute(
                    text("SELECT set_config('app.current_org_id', :org, true)"),
                    {"org": str(first["org_id"])},
                )
                visible_year_ends = (
                    session.execute(text("SELECT id FROM findraft_year_ends"))
                    .scalars()
                    .all()
                )
                assert [str(item) for item in visible_year_ends] == [
                    str(first["year_end_id"])
                ]
                updated = session.execute(
                    text(
                        """
                        UPDATE findraft_year_ends
                        SET adopted_trial_balance_id = :tb
                        WHERE id = :year_end
                        """
                    ),
                    {
                        "tb": str(first_tb),
                        "year_end": str(first["year_end_id"]),
                    },
                )
                assert updated.rowcount == 1
                hidden = session.execute(
                    text(
                        """
                        UPDATE findraft_year_ends
                        SET adopted_trial_balance_id = :tb
                        WHERE id = :year_end
                        """
                    ),
                    {
                        "tb": str(second_tb),
                        "year_end": str(second["year_end_id"]),
                    },
                )
                assert hidden.rowcount == 0
                with pytest.raises(
                    DBAPIError,
                    match="adopted trial balance belongs to another company",
                ):
                    session.execute(
                        text(
                            """
                            UPDATE findraft_year_ends
                            SET adopted_trial_balance_id = :tb
                            WHERE id = :year_end
                            """
                        ),
                        {
                            "tb": str(second_tb),
                            "year_end": str(first["year_end_id"]),
                        },
                    )
                session.rollback()
                session.execute(text("SET ROLE findraft_app"))
                session.execute(
                    text("SELECT set_config('app.current_org_id', :org, true)"),
                    {"org": str(first["org_id"])},
                )
                with pytest.raises(
                    DBAPIError, match="adopted trial balance is not an active"
                ):
                    session.execute(
                        text(
                            """
                            UPDATE findraft_year_ends
                            SET adopted_trial_balance_id = :tb
                            WHERE id = :year_end
                            """
                        ),
                        {
                            "tb": str(uuid.uuid4()),
                            "year_end": str(first["year_end_id"]),
                        },
                    )
            finally:
                session.rollback()
                session.execute(text("RESET ROLE"))
        with SyncSessionLocal() as session:
            set_rls_org_id(session, first["org_id"])
            with pytest.raises(
                DBAPIError, match="adopted trial balance belongs to another company"
            ):
                session.execute(
                    text(
                        """
                        UPDATE findraft_year_ends
                        SET adopted_trial_balance_id = :tb
                        WHERE id = :year_end
                        """
                    ),
                    {
                        "tb": str(second_tb),
                        "year_end": str(first["year_end_id"]),
                    },
                )
            session.rollback()
    finally:
        _delete_org(first["org_id"])
        _delete_org(second["org_id"])


def _year_end_row(
    company_id: uuid.UUID, period_end: date, org_id: uuid.UUID
) -> tuple[str, str | None] | None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.execute(
            text(
                "SELECT id::text, adopted_trial_balance_id::text "
                "FROM findraft_year_ends "
                "WHERE company_id = :company AND period_end = :period"
            ),
            {"company": str(company_id), "period": period_end},
        ).one_or_none()
    if row is None:
        return None
    return str(row[0]), None if row[1] is None else str(row[1])


_CASH_PAIR = (
    ("2130", "Bank current account", "100.00", "0.00", "100.00", "cash"),
    (
        "3000",
        "Called up share capital",
        "0.00",
        "100.00",
        "-100.00",
        "share_capital",
    ),
)


@pytest.mark.asyncio
async def test_statements_trial_balance_opens_a_statutory_year_end(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """The statements page adopts the TB already loaded. No statutory copy."""
    year_end_id = await _year_end(api_client, provisioned_org)
    tb_id = _insert_tb(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        rows=_golden_rows(),
        period_start=date(2026, 1, 1),
    )
    headers = auth_headers(provisioned_org["token"])
    first = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["year_end_id"] == year_end_id
    assert body["trial_balance_id"] == str(tb_id)
    assert {
        line["nominal_code"]: line["canonical_line"] for line in body["lines"]
    } == _MAPPINGS
    assert _pointer(year_end_id, provisioned_org["org_id"]) == str(tb_id)
    assert _statutory_copy_counts(provisioned_org["org_id"], year_end_id) == (0, 0)

    second = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={"pack_id": "frs102-1a-ie", "pack_version": "2024.09"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["year_end_id"] == year_end_id
    assert _statutory_copy_counts(provisioned_org["org_id"], year_end_id) == (0, 0)

    blocked = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["renderable"] is False
    assert any(
        check["code"] == "V-GATE-001" and check["passed"] is False
        for check in blocked.json()["checks"]
    )
    refused_pdf = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
        headers=headers,
    )
    assert refused_pdf.status_code == 400, refused_pdf.text
    assert refused_pdf.json()["detail"] == "Statutory statements are not renderable"

    opened = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert opened.status_code == 200, opened.text
    statements = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert statements.status_code == 200, statements.text
    assert _statutory_copy_counts(provisioned_org["org_id"], year_end_id) == (0, 0)


@pytest.mark.asyncio
async def test_statutory_continuation_creates_the_year_end_when_missing(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    tb_id = _insert_tb(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        rows=_CASH_PAIR,
        period_start=date(2026, 1, 1),
    )
    headers = auth_headers(provisioned_org["token"])
    missing = await api_client.get(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
    )
    assert missing.status_code == 404, missing.text
    response = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert response.status_code == 200, response.text
    stored = _year_end_row(
        provisioned_org["company_id"], date(2026, 12, 31), provisioned_org["org_id"]
    )
    assert stored is not None
    assert stored[0] == response.json()["year_end_id"]
    assert stored[1] == str(tb_id)
    assert _statutory_copy_counts(provisioned_org["org_id"], stored[0]) == (0, 0)
    link = await api_client.get(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
    )
    assert link.status_code == 200, link.text
    assert link.json()["year_end_id"] == response.json()["year_end_id"]
    loaded = await api_client.get(
        f"/year-ends/{response.json()['year_end_id']}",
        headers=headers,
    )
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["period_start"] == "2026-01-01"
    assert loaded.json()["adopted_trial_balance_id"] == str(tb_id)
    draft = await api_client.get(
        f"/year-ends/{response.json()['year_end_id']}/draft",
        headers=headers,
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["tb_version_id"] is None
    assert draft.json()["version_number"] == 1
    assert draft.json()["mapping_notice"] is None
    assert draft.json()["frozen"] is False
    assert _draft_count(response.json()["year_end_id"], provisioned_org["org_id"]) == 1
    again = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert again.status_code == 200, again.text
    assert _draft_count(response.json()["year_end_id"], provisioned_org["org_id"]) == 1
    assert _statutory_copy_counts(provisioned_org["org_id"], stored[0]) == (0, 0)
    unknown = await api_client.get(
        f"/year-ends/{uuid.uuid4()}",
        headers=headers,
    )
    assert unknown.status_code == 404, unknown.text
    catalogue = await api_client.get("/year-ends/canonical-lines", headers=headers)
    assert catalogue.status_code == 200, catalogue.text


@pytest.mark.asyncio
async def test_statutory_continuation_refuses_unconfirmed_incomplete_and_early_periods(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]

    unconfirmed = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=_CASH_PAIR,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        confirmed=False,
    )
    refused = await api_client.post(
        f"/trial-balances/{unconfirmed}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert refused.status_code == 400, refused.text
    assert "is not confirmed" in refused.json()["detail"]
    assert _year_end_row(company_id, date(2026, 12, 31), org_id) is None

    incomplete = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(
            ("2131", "Deposit account", "40.00", "0.00", "40.00", "cash"),
            ("3001", "Ordinary shares", "0.00", "40.00", "-40.00", "share_capital"),
        ),
        status="mapping",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
    )
    not_ready = await api_client.post(
        f"/trial-balances/{incomplete}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert not_ready.status_code == 400, not_ready.text
    assert "not a completed" in not_ready.json()["detail"]
    assert _year_end_row(company_id, date(2026, 6, 30), org_id) is None

    missing_start = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(
            ("2132", "Petty cash", "5.00", "0.00", "5.00", "cash"),
            ("3003", "Founder shares", "0.00", "5.00", "-5.00", "share_capital"),
        ),
        period_end=date(2026, 9, 30),
    )
    no_start = await api_client.post(
        f"/trial-balances/{missing_start}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert no_start.status_code == 400, no_start.text
    assert no_start.json()["detail"] == "This trial balance has no period start"
    assert _year_end_row(company_id, date(2026, 9, 30), org_id) is None

    early = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(
            ("2134", "Cash float", "12.00", "0.00", "12.00", "cash"),
            ("3005", "Subscriber shares", "0.00", "12.00", "-12.00", "share_capital"),
        ),
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
    )
    too_early = await api_client.post(
        f"/trial-balances/{early}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert too_early.status_code == 400, too_early.text
    assert "2026-01-01" in too_early.json()["detail"]
    assert _year_end_row(company_id, date(2025, 12, 31), org_id) is None


@pytest.mark.asyncio
async def test_statutory_continuation_refuses_a_different_pinned_pack(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                """
                INSERT INTO findraft_year_ends (
                  id, org_id, company_id, period_start, period_end,
                  pack_id, pack_version
                ) VALUES (
                  :id, :org, :company, DATE '2026-01-01', DATE '2026-12-31',
                  'other-pack', '1999.01'
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "org": str(org_id),
                "company": str(company_id),
            },
        )
        session.commit()
    tb_id = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=_CASH_PAIR,
        period_start=date(2026, 1, 1),
    )
    response = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=auth_headers(provisioned_org["token"]),
        json={},
    )
    assert response.status_code == 409, response.text
    assert "other-pack 1999.01" in response.json()["detail"]
    stored = _year_end_row(company_id, date(2026, 12, 31), org_id)
    assert stored is not None
    assert stored[1] is None


def _draft_version(draft_id: str, org_id: uuid.UUID) -> int:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        value = session.execute(
            text("SELECT row_version FROM findraft_draft_versions WHERE id = :id"),
            {"id": draft_id},
        ).scalar_one()
    return int(value)


_FILE_HASH = "ab" * 32


def _set_file_hash(tb_id: uuid.UUID, org_id: uuid.UUID, digest: str) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text("UPDATE trial_balances SET file_hash = :digest WHERE id = :id"),
            {"digest": digest, "id": str(tb_id)},
        )
        session.commit()


def _snapshot(draft_id: str, org_id: uuid.UUID) -> dict[str, object] | None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        value = session.execute(
            text("SELECT snapshot FROM findraft_draft_versions WHERE id = :id"),
            {"id": draft_id},
        ).scalar_one()
    if value is None:
        return None
    assert isinstance(value, dict)
    return value


def _answer_all_no(*, org_id: uuid.UUID, company_id: uuid.UUID, draft_id: str) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        for name in sorted(ANSWER_FLAGS):
            session.add(
                DisclosureAnswer(
                    org_id=org_id,
                    company_id=company_id,
                    draft_version_id=uuid.UUID(draft_id),
                    flag_name=name,
                    answer=False,
                )
            )
        session.commit()


async def _record_letterhead(
    api_client: AsyncClient, headers: dict[str, str], year_end_id: str
) -> None:
    saved = await api_client.put(
        f"/year-ends/{year_end_id}/company-details",
        headers=headers,
        json={
            "registered_office": "1 Harbour Street, Dublin",
            "company_number": "AB123456",
            "directors": [{"name": "Ada Lovelace"}],
        },
    )
    assert saved.status_code == 200, saved.text
    approved = await api_client.put(
        f"/year-ends/{year_end_id}/approval",
        headers=headers,
        json={
            "approval_date": "2027-03-15",
            "signing_directors": ["Ada Lovelace"],
        },
    )
    assert approved.status_code == 200, approved.text


async def _open_adopted(
    api_client: AsyncClient,
    provisioned_org: dict,
    *,
    rows: tuple[tuple[str, str, str, str, str, str], ...],
) -> tuple[str, str, dict[str, str]]:
    tb_id = _insert_tb(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        rows=rows,
        period_start=date(2026, 1, 1),
    )
    _set_file_hash(tb_id, provisioned_org["org_id"], _FILE_HASH)
    headers = auth_headers(provisioned_org["token"])
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = opened.json()["year_end_id"]
    period = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert period.status_code == 200, period.text
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    return year_end_id, draft.json()["draft_id"], headers


@pytest.mark.asyncio
async def test_adopted_draft_adjusts_discloses_notices_and_starts_a_new_report(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """Continuation draft: live mappings, saved work, and a frozen predecessor."""
    tb_id = _insert_tb(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        rows=_CASH_PAIR,
        period_start=date(2026, 1, 1),
    )
    headers = auth_headers(provisioned_org["token"])
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = opened.json()["year_end_id"]
    assert _statutory_copy_counts(provisioned_org["org_id"], year_end_id) == (0, 0)
    gate = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert gate.status_code == 200, gate.text
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    first_id = draft.json()["draft_id"]
    board = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{first_id}/dashboard",
        headers=headers,
    )
    assert board.status_code == 200, board.text
    before = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert before.status_code == 200, before.text
    assert before.json()["renderable"] is True, before.text
    profit_before = before.json()["profit"]
    assets_before = before.json()["net_assets"]
    posted = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{first_id}/adjustments",
        headers={**headers, "Idempotency-Key": "adopted-admin-overhead"},
        json={
            "row_version": draft.json()["row_version"],
            "narration": "Admin overhead",
            "lines": [
                {
                    "nominal_code": "7100",
                    "account_name": "Admin overhead",
                    "canonical_line": "ADMIN_EXPENSES",
                    "debit": "10.00",
                    "credit": "0.00",
                },
                {
                    "nominal_code": "7200",
                    "account_name": "Sundry creditor",
                    "canonical_line": "OTHER_CREDITORS",
                    "debit": "0.00",
                    "credit": "10.00",
                },
            ],
        },
    )
    assert posted.status_code == 200, posted.text
    assert _child_count(
        "findraft_adjustment_journals", first_id, provisioned_org["org_id"]
    ) == 1
    moved = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["renderable"] is True, moved.text
    assert Decimal(moved.json()["profit"]) != Decimal(profit_before)
    assert Decimal(moved.json()["net_assets"]) != Decimal(assets_before)
    answered = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{first_id}/disclosures",
        headers=headers,
        json={
            "row_version": posted.json()["row_version"],
            "flag_name": "HAS_EMPLOYEES",
            "answer": "no",
        },
    )
    assert answered.status_code == 200, answered.text
    assert _child_count(
        "findraft_disclosure_answers", first_id, provisioned_org["org_id"]
    ) == 1
    recomputed = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{first_id}/recompute",
        headers={**headers, "Idempotency-Key": "adopted-recompute"},
        json={"row_version": answered.json()["row_version"]},
    )
    assert recomputed.status_code == 200, recomputed.text
    _remap(
        provisioned_org["company_id"],
        "2130",
        "other_receivables",
        provisioned_org["org_id"],
    )
    noticed = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert noticed.status_code == 200, noticed.text
    assert noticed.json()["mapping_notice"] == (
        "Product 1 confirmed mappings changed after this draft was acknowledged. "
        "This draft now uses the current mappings."
    )
    remapped = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert remapped.status_code == 200, remapped.text
    assert remapped.json()["renderable"] is True, remapped.text
    cash_when_remapped = _sofp_amount(remapped.json(), "Cash at bank and in hand")
    acknowledged = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{first_id}/acknowledge-mappings",
        headers=headers,
        json={"row_version": noticed.json()["row_version"]},
    )
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["row_version"] == noticed.json()["row_version"] + 1
    cleared = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["mapping_notice"] is None
    started = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{first_id}/new-report",
        headers=headers,
        json={"row_version": cleared.json()["row_version"]},
    )
    assert started.status_code == 200, started.text
    second_id = started.json()["draft_id"]
    assert second_id != first_id
    assert started.json()["version_number"] == 2
    assert _frozen_mapping(first_id, "2130", provisioned_org["org_id"]) == "OTHER_DEBTORS"
    assert _child_count(
        "findraft_adjustment_journals", first_id, provisioned_org["org_id"]
    ) == 1
    assert _child_count(
        "findraft_adjustment_journals", second_id, provisioned_org["org_id"]
    ) == 0
    assert _child_count(
        "findraft_disclosure_answers", first_id, provisioned_org["org_id"]
    ) == 1
    assert _child_count(
        "findraft_disclosure_answers", second_id, provisioned_org["org_id"]
    ) == 0
    _remap(
        provisioned_org["company_id"], "2130", "cash", provisioned_org["org_id"]
    )
    active = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert active.status_code == 200, active.text
    assert active.json()["renderable"] is True, active.text
    assert _sofp_amount(active.json(), "Cash at bank and in hand") != cash_when_remapped
    assert _frozen_mapping(first_id, "2130", provisioned_org["org_id"]) == "OTHER_DEBTORS"
    current = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert current.status_code == 200, current.text
    assert current.json()["draft_id"] == second_id
    assert current.json()["mapping_notice"] == (
        "Product 1 confirmed mappings changed after this draft was acknowledged. "
        "This draft now uses the current mappings."
    )
    stale = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{first_id}/new-report",
        headers=headers,
        json={"row_version": _draft_version(first_id, provisioned_org["org_id"])},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"] == "This draft is not the active report"
    history = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{first_id}/dashboard",
        headers=headers,
    )
    assert history.status_code == 200, history.text
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{second_id}/finalise",
        headers={**headers, "Idempotency-Key": "adopted-finalise"},
        json={"row_version": current.json()["row_version"]},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == "Directors have not been recorded."
    assert _snapshot(second_id, provisioned_org["org_id"]) is None
    assert _statutory_copy_counts(provisioned_org["org_id"], year_end_id) == (0, 0)
    assert _draft_count(year_end_id, provisioned_org["org_id"]) == 2


@pytest.mark.asyncio
async def test_unresolved_subline_blocks_the_draft_until_confirmed(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """A generic name opens the draft and does not pick a statutory line."""
    rows = (
        ("6000", "Operating Expenses", "80.00", "0.00", "80.00", "operating_expenses"),
        ("7100", "Amortisation charge", "20.00", "0.00", "20.00", "amortisation"),
        (
            "3000",
            "Called up share capital",
            "0.00",
            "100.00",
            "-100.00",
            "share_capital",
        ),
    )
    tb_id = _insert_tb(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        rows=rows,
        period_start=date(2026, 1, 1),
        confirm_sublines=False,
    )
    headers = auth_headers(provisioned_org["token"])
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = opened.json()["year_end_id"]
    by_code = {line["nominal_code"]: line for line in opened.json()["lines"]}
    assert by_code["6000"]["canonical_line"] == ""
    assert by_code["6000"]["suggested_line"] is None
    assert by_code["7100"]["canonical_line"] == ""
    assert by_code["7100"]["suggested_line"] == "AMORTISATION_CHARGE"
    assert by_code["7100"]["suggestion_confidence"] == "0.40"
    opened_gate = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert opened_gate.status_code == 200, opened_gate.text
    blocked = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert blocked.status_code == 400, blocked.text
    assert blocked.json()["detail"] == (
        "Product 1 line 'operating_expenses' on 'Operating Expenses' "
        "needs a statutory sub-line"
    )
    blocked_pdf = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
        headers=headers,
    )
    assert blocked_pdf.status_code == 400, blocked_pdf.text
    assert blocked_pdf.json()["detail"] == blocked.json()["detail"]
    review = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/sub-lines",
        headers=headers,
    )
    assert review.status_code == 200, review.text
    assert review.json()["blocked"] is True
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/adopted-trial-balance/sub-lines",
        headers=headers,
        json={
            "lines": [
                {
                    "nominal_code": "6000",
                    "account_name": "Operating Expenses",
                    "statutory_line": "REVENUE",
                }
            ]
        },
    )
    assert refused.status_code == 400, refused.text
    confirmed = await api_client.post(
        f"/year-ends/{year_end_id}/adopted-trial-balance/sub-lines",
        headers=headers,
        json={
            "lines": [
                {
                    "nominal_code": "6000",
                    "account_name": "Operating Expenses",
                    "statutory_line": "ADMIN_EXPENSES",
                },
                {
                    "nominal_code": "7100",
                    "account_name": "Amortisation charge",
                    "statutory_line": "AMORTISATION_CHARGE",
                },
            ]
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["blocked"] is False
    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        stored = session.execute(
            text(
                "SELECT canonical_line, statutory_line FROM account_mappings "
                "WHERE company_id = :company AND source_code = '6000'"
            ),
            {"company": str(provisioned_org["company_id"])},
        ).one()
    assert stored[0] == "operating_expenses"
    assert stored[1] == "ADMIN_EXPENSES"
    statements = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert statements.status_code == 200, statements.text
    body = statements.json()
    admin = next(
        row
        for row in body["income"]
        if row["label"] == "Administrative expenses (including depreciation)"
    )
    assert admin["current"] == "-100.00"
    assert body["profit"] == "-100.00"
    assert all(row["label"] != "Amortisation charge" for row in body["income"])
    anonymous = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
    )
    assert anonymous.status_code == 401, anonymous.text
    pdf = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
        headers=headers,
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert (
        pdf.headers["content-disposition"]
        == 'attachment; filename="statutory-statements-draft.pdf"'
    )
    assert pdf.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_adopted_draft_word_export_is_draft_without_tb_version(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    tb_id = _insert_tb(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        rows=_CASH_PAIR,
        period_start=date(2026, 1, 1),
    )
    headers = auth_headers(provisioned_org["token"])
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = opened.json()["year_end_id"]
    period = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert period.status_code == 200, period.text
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    assert draft.json()["tb_version_id"] is None
    draft_id = draft.json()["draft_id"]
    created = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/document.docx",
        headers={**headers, "Idempotency-Key": "adopted-word"},
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["job_id"]
    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        stored = session.execute(
            text(
                "SELECT tb_version_id::text, draft_id::text, watermark "
                "FROM findraft_render_jobs WHERE id = :id"
            ),
            {"id": job_id},
        ).one()
    assert stored[0] is None
    assert stored[1] == draft_id
    assert stored[2] == "DRAFT"
    with SyncSessionLocal() as session:
        processed = process_render_job(
            session,
            org_id=provisioned_org["org_id"],
            job_id=uuid.UUID(job_id),
            storage=stored_files,
        )
    if processed is None:
        with SyncSessionLocal() as session:
            set_rls_org_id(session, provisioned_org["org_id"])
            stored_job = session.execute(
                text(
                    "SELECT status, storage_key, error_message "
                    "FROM findraft_render_jobs WHERE id = :id"
                ),
                {"id": job_id},
            ).one()
        assert stored_job[0] == "ready", stored_job[2]
        assert stored_job[1] is not None
        content = stored_files.get(key=stored_job[1])
    else:
        assert processed.status == "ready", processed.error_message
        assert processed.storage_key is not None
        content = stored_files.get(key=processed.storage_key)
    assert content.startswith(b"PK")
    with zipfile.ZipFile(BytesIO(content)) as archive:
        xml = archive.read("word/document.xml").decode()
        header_parts = [
            archive.read(name).decode()
            for name in archive.namelist()
            if name.startswith("word/header")
        ]
    assert header_parts
    assert all("DRAFT" in header and "FINAL" not in header for header in header_parts)
    assert "DRAFT" not in xml
    assert "FINAL" not in xml
    replay = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/document.docx",
        headers={**headers, "Idempotency-Key": "adopted-word"},
    )
    assert replay.status_code == 202, replay.text
    assert replay.json()["job_id"] == job_id


def _pdf_text(payload: bytes) -> str:
    exe = shutil.which("pdftotext")
    assert exe is not None, "pdftotext is not installed"
    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(payload)
        handle.flush()
        completed = subprocess.run(
            [exe, "-layout", handle.name, "-"],
            check=True,
            capture_output=True,
        )
    return completed.stdout.decode("utf-8")


def _refuse_draft_change(
    org_id: uuid.UUID,
    draft_id: str,
    assignment: str,
    match: str,
    extra: dict[str, object] | None = None,
) -> None:
    params: dict[str, object] = {"id": draft_id}
    if extra is not None:
        params.update(extra)
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        with pytest.raises(DBAPIError, match=match):
            session.execute(
                text(
                    f"UPDATE findraft_draft_versions SET {assignment} WHERE id = :id"
                ),
                params,
            )
            session.commit()
        session.rollback()


def _source_documents(org_id: uuid.UUID) -> int:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        count = session.execute(
            text("SELECT count(*) FROM findraft_source_documents WHERE org_id = :org"),
            {"org": str(org_id)},
        ).scalar_one()
    return int(count)


async def _ready_golden(
    api_client: AsyncClient, provisioned_org: dict
) -> tuple[str, str, dict[str, str]]:
    """Golden chart with the opening reserve confirmed as the prior year.

    A first period stores no opening reserve, so the roll-forward check
    would stay critical. Confirming that credit lets FINAL proceed.
    """
    tb_id = _insert_tb(
        org_id=provisioned_org["org_id"],
        company_id=provisioned_org["company_id"],
        rows=_golden_rows(),
        period_start=date(2026, 1, 1),
    )
    _set_file_hash(tb_id, provisioned_org["org_id"], _FILE_HASH)
    headers = auth_headers(provisioned_org["token"])
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = opened.json()["year_end_id"]
    prior = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json={"lines": [{"canonical_line": "RETAINED_EARNINGS", "amount": "-322062.00"}]},
    )
    assert prior.status_code == 200, prior.text
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    draft_id = draft.json()["draft_id"]
    await _record_letterhead(api_client, headers, year_end_id)
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
    return year_end_id, draft_id, headers


@pytest.mark.asyncio
async def test_finalised_adopted_draft_ignores_a_later_mapping_edit(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    """Product 1 edits after FINAL do not change the stored PDF or Word file."""
    year_end_id, draft_id, headers = await _ready_golden(api_client, provisioned_org)
    before = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert before.status_code == 200, before.text
    cash_before = _sofp_amount(before.json(), "Cash at bank and in hand")
    reserves_before = _sofp_amount(before.json(), "Profit and loss account")
    finalised = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/finalise",
        headers={**headers, "Idempotency-Key": "adopted-final-snapshot"},
        json={"row_version": _draft_version(draft_id, provisioned_org["org_id"])},
    )
    assert finalised.status_code == 200, finalised.text
    assert finalised.json()["status"] == "final"
    stored = _snapshot(draft_id, provisioned_org["org_id"])
    assert stored is not None
    assert stored["html"]
    assert stored["composed_html"]
    assert stored["html"] != stored["composed_html"]
    sections = stored["composed_sections"]
    assert isinstance(sections, list) and sections
    current = stored["canonical_current"]
    assert isinstance(current, dict)
    closing = Decimal(str(current["RETAINED_EARNINGS"]))
    print(f"canonical_current RETAINED_EARNINGS={closing}")
    assert closing == Decimal("455712.00")
    assert closing != Decimal("322062.00")
    assert closing == Decimal(reserves_before)
    evidence = stored["evidence"]
    assert isinstance(evidence, dict)
    documents = evidence["documents"]
    assert isinstance(documents, list) and len(documents) == 1
    assert documents[0]["file_hash"] == _FILE_HASH
    assert documents[0]["filename"] == _FILE_HASH
    assert "file://" not in str(evidence)
    lines = evidence["lines"]
    assert isinstance(lines, list)
    codes: list[str] = []
    for line in lines:
        assert isinstance(line, dict)
        accounts = line["accounts"]
        assert isinstance(accounts, list)
        for account in accounts:
            assert isinstance(account, dict)
            assert account["source_document_id"] is None
            assert account["tb_line_id"] is None
            codes.append(str(account["nominal_code"]))
    assert "2130" in codes
    assert "3100" in codes
    assert _source_documents(provisioned_org["org_id"]) == 0
    _remap(
        provisioned_org["company_id"],
        "2130",
        "other_receivables",
        provisioned_org["org_id"],
    )
    after = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert after.status_code == 200, after.text
    assert _sofp_amount(after.json(), "Cash at bank and in hand") == cash_before
    assert after.json()["profit"] == before.json()["profit"]
    pdf = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
        headers=headers,
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF")
    assert pdf.headers["content-disposition"].endswith(
        'filename="statutory-statements-final.pdf"'
    )
    composed = stored["composed_html"]
    assert isinstance(composed, str)
    # WeasyPrint stamps a fresh document id, so two renders of the same
    # HTML are not byte-identical. The extracted face still shows the cash
    # that was frozen before the Product 1 remap.
    rendered = _pdf_text(pdf.content)
    assert "284,912" in rendered
    assert "FINAL" in rendered
    created = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/document.docx",
        headers={**headers, "Idempotency-Key": "adopted-final-word"},
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["job_id"]
    with SyncSessionLocal() as session:
        processed = process_render_job(
            session,
            org_id=provisioned_org["org_id"],
            job_id=uuid.UUID(job_id),
            storage=stored_files,
        )
    if processed is None:
        with SyncSessionLocal() as session:
            set_rls_org_id(session, provisioned_org["org_id"])
            stored_job = session.execute(
                text(
                    "SELECT status, storage_key, error_message "
                    "FROM findraft_render_jobs WHERE id = :id"
                ),
                {"id": job_id},
            ).one()
        assert stored_job[0] == "ready", stored_job[2]
        assert stored_job[1] is not None
        content = stored_files.get(key=stored_job[1])
    else:
        assert processed.status == "ready", processed.error_message
        assert processed.storage_key is not None
        content = stored_files.get(key=processed.storage_key)
    with zipfile.ZipFile(BytesIO(content)) as archive:
        xml = archive.read("word/document.xml").decode()
        header_parts = [
            archive.read(name).decode()
            for name in archive.namelist()
            if name.startswith("word/header")
        ]
    assert header_parts
    assert all("FINAL" in header and "DRAFT" not in header for header in header_parts)
    assert "284,912" in xml


@pytest.mark.asyncio
async def test_member_cannot_finalise_an_adopted_draft(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    year_end_id, draft_id, _headers = await _open_adopted(
        api_client, provisioned_org, rows=_CASH_PAIR
    )
    _user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="finalise-member",
    )
    member = auth_headers(
        make_access_token(
            clerk_user_id=clerk_user_id,
            clerk_org_id=provisioned_org["clerk_org_id"],
            role="owner",
            org_uuid=provisioned_org["org_id"],
        )
    )
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/finalise",
        headers={**member, "Idempotency-Key": "member-finalise"},
        json={"row_version": _draft_version(draft_id, provisioned_org["org_id"])},
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"] == _FORBIDDEN
    assert _snapshot(draft_id, provisioned_org["org_id"]) is None


@pytest.mark.asyncio
async def test_missing_directors_block_finalise_without_a_snapshot(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    year_end_id, draft_id, headers = await _open_adopted(
        api_client, provisioned_org, rows=_CASH_PAIR
    )
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/finalise",
        headers={**headers, "Idempotency-Key": "missing-directors"},
        json={"row_version": _draft_version(draft_id, provisioned_org["org_id"])},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == "Directors have not been recorded."
    assert _snapshot(draft_id, provisioned_org["org_id"]) is None


@pytest.mark.asyncio
async def test_frozen_adopted_draft_finalises_from_frozen_inputs(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """A report started later does not change the frozen draft's FINAL figures."""
    year_end_id, first_id, headers = await _ready_golden(api_client, provisioned_org)
    before = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert before.status_code == 200, before.text
    cash_before = _sofp_amount(before.json(), "Cash at bank and in hand")
    started = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{first_id}/new-report",
        headers=headers,
        json={"row_version": _draft_version(first_id, provisioned_org["org_id"])},
    )
    assert started.status_code == 200, started.text
    _remap(
        provisioned_org["company_id"],
        "2130",
        "other_receivables",
        provisioned_org["org_id"],
    )
    active = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert active.status_code == 200, active.text
    assert _sofp_amount(active.json(), "Cash at bank and in hand") != cash_before
    finalised = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{first_id}/finalise",
        headers={**headers, "Idempotency-Key": "frozen-finalise"},
        json={"row_version": _draft_version(first_id, provisioned_org["org_id"])},
    )
    assert finalised.status_code == 200, finalised.text
    stored = _snapshot(first_id, provisioned_org["org_id"])
    assert stored is not None
    statement = stored["statement"]
    assert isinstance(statement, dict)
    assert _sofp_amount(statement, "Cash at bank and in hand") == cash_before
    still_live = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert still_live.status_code == 200, still_live.text
    assert _sofp_amount(still_live.json(), "Cash at bank and in hand") != cash_before
    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        with pytest.raises(DBAPIError, match="frozen draft is immutable"):
            session.execute(
                text(
                    "UPDATE findraft_draft_versions SET is_frozen = false WHERE id = :id"
                ),
                {"id": first_id},
            )
            session.commit()
        session.rollback()


@pytest.mark.asyncio
async def test_frozen_status_guard_refuses_every_other_change(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """The guard allows one frozen transition: draft to final. Nothing else."""
    year_end_id, first_id, headers = await _open_adopted(
        api_client, provisioned_org, rows=_CASH_PAIR
    )
    started = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{first_id}/new-report",
        headers=headers,
        json={"row_version": _draft_version(first_id, provisioned_org["org_id"])},
    )
    assert started.status_code == 200, started.text
    org_id = provisioned_org["org_id"]
    _refuse_draft_change(
        org_id, first_id, "is_frozen = false", "frozen draft is immutable"
    )
    _refuse_draft_change(
        org_id,
        first_id,
        "frozen_inputs = '{\"replaced\": true}'::jsonb",
        "frozen draft is immutable",
    )
    _refuse_draft_change(
        org_id,
        first_id,
        "mappings_sha256 = :sha",
        "frozen draft is immutable",
        {"sha": "c" * 64},
    )
    _refuse_draft_change(
        org_id, first_id, "status = 'locked'", "frozen draft is immutable"
    )
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        updated = session.execute(
            text(
                """
                UPDATE findraft_draft_versions
                SET status = 'final',
                    snapshot = '{"watermark": "FINAL"}'::jsonb,
                    inputs_sha256 = :inputs,
                    engine_sha = :engine
                WHERE id = :id
                """
            ),
            {
                "id": first_id,
                "inputs": "a" * 64,
                "engine": "b" * 64,
            },
        )
        assert updated.rowcount == 1
        session.commit()
    for assignment, match, extra in (
        ("status = 'draft'", "FINAL draft is immutable", None),
        ("status = 'locked'", "FINAL draft is immutable", None),
        (
            "snapshot = '{\"watermark\": \"CHANGED\"}'::jsonb",
            "FINAL draft is immutable",
            None,
        ),
        ("inputs_sha256 = :sha", "FINAL draft is immutable", {"sha": "d" * 64}),
        ("engine_sha = :sha", "FINAL draft is immutable", {"sha": "e" * 64}),
        ("pack_id = 'other-pack'", "FINAL draft is immutable", None),
        ("pack_version = '1999.01'", "FINAL draft is immutable", None),
        ("is_frozen = false", "frozen draft is immutable", None),
        (
            "frozen_inputs = '{\"replaced\": true}'::jsonb",
            "frozen draft is immutable",
            None,
        ),
        ("mappings_sha256 = :sha", "frozen draft is immutable", {"sha": "f" * 64}),
    ):
        _refuse_draft_change(org_id, first_id, assignment, match, extra)


@pytest.mark.asyncio
async def test_carried_disclosure_answers_need_an_acknowledgement(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    year_end_id, draft_id, headers = await _ready_golden(api_client, provisioned_org)
    locked = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/lock",
        headers=headers,
        json={"row_version": _draft_version(draft_id, provisioned_org["org_id"])},
    )
    assert locked.status_code == 200, locked.text
    created = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/new-version",
        headers=headers,
        json={"row_version": locked.json()["row_version"]},
    )
    assert created.status_code == 200, created.text
    child_id = created.json()["draft_id"]
    child_board = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{child_id}/dashboard",
        headers=headers,
    )
    assert child_board.status_code == 200, child_board.text
    assert "HAS_EMPLOYEES" in child_board.json()["carried_disclosures"]
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{child_id}/finalise",
        headers={**headers, "Idempotency-Key": "carried-without-ack"},
        json={"row_version": created.json()["row_version"]},
    )
    assert refused.status_code == 409, refused.text
    assert (
        refused.json()["detail"]
        == "Carried-over disclosure answers have not been acknowledged."
    )
    assert _snapshot(child_id, provisioned_org["org_id"]) is None
    finalised = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{child_id}/finalise",
        headers={**headers, "Idempotency-Key": "carried-with-ack"},
        json={
            "row_version": created.json()["row_version"],
            "reviewed_carried_disclosures": True,
        },
    )
    assert finalised.status_code == 200, finalised.text
    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        recorded = session.execute(
            text(
                "SELECT new_value FROM audit_logs WHERE org_id = :org "
                "AND entity_id = :draft AND action = 'carried_disclosures_reviewed'"
            ),
            {"org": str(provisioned_org["org_id"]), "draft": child_id},
        ).scalar_one()
    assert isinstance(recorded, dict)
    assert recorded["reviewed"] is True
    assert "HAS_EMPLOYEES" in recorded["flag_names"]
