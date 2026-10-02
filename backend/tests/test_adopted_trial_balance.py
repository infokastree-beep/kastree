"""Adopt a completed Product 1 trial balance into a statutory year end.

The year end stores trial_balances.id. No findraft_tb_versions row is
created, and account_mappings are not copied into findraft_confirmed_mappings.
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


def test_golden_chart_translates_to_the_engine_map() -> None:
    carried = {
        code: engine_line_for_confirmed_mapping(_PRODUCT1[code], name)
        for code, name, _debit, _credit in _TB
    }
    assert carried == _MAPPINGS


def test_coarse_lines_without_one_statutory_home_are_refused() -> None:
    refused = (
        ("loans", "Bank loan"),
        ("operating_expenses", "Rent"),
        ("gross_profit", "Sales revenue"),
        ("amortisation", "Amortisation charge"),
        ("unmapped", "Sundry"),
        ("property_plant_equipment", "Sundry asset"),
    )
    for product1_line, account_name in refused:
        with pytest.raises(ReconciliationRejected, match="no single statutory line"):
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
    confirmed: bool = True,
) -> uuid.UUID:
    tb_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            TrialBalance(
                id=tb_id,
                company_id=company_id,
                period_end=period_end,
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


def _retire(tb_id: uuid.UUID) -> None:
    with SyncSessionLocal() as session:
        session.execute(
            text(
                "UPDATE trial_balances "
                "SET is_deleted = true, deleted_at = NOW() WHERE id = :id"
            ),
            {"id": str(tb_id)},
        )
        session.commit()


def _pointer(year_end_id: str) -> str | None:
    with SyncSessionLocal() as session:
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


def _statutory_copy_counts(org_id: uuid.UUID, year_end_id: str) -> tuple[int, int]:
    with SyncSessionLocal() as session:
        versions = session.execute(
            text(
                "SELECT count(*) FROM findraft_tb_versions WHERE year_end_id = :id"
            ),
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
    assert _pointer(year_end_id) == str(tb_id)
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
    pdf = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
        headers=headers,
    )
    assert pdf.status_code == 200, pdf.text
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
        (
            (
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
            {"status": "complete", "confirmed": True},
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
        assert _pointer(year_end_id) is None
        _retire(tb_id)

    for tb_id, status in ((other_period, 400), (other_tb, 404), (uuid.uuid4(), 404)):
        response = await api_client.post(
            f"/year-ends/{year_end_id}/adopt-trial-balance",
            headers=headers,
            json={"trial_balance_id": str(tb_id)},
        )
        assert response.status_code == status, response.text
        assert _pointer(year_end_id) is None


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
    _set_role(
        org_id=provisioned_org["org_id"], user_id=user_id, role="viewer"
    )
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


def _insert_bare_tb(company_id: uuid.UUID) -> uuid.UUID:
    tb_id = uuid.uuid4()
    with SyncSessionLocal() as session:
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
    first_tb = _insert_bare_tb(first["company_id"])
    second_tb = _insert_bare_tb(second["company_id"])
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
