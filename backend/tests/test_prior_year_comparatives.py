"""Prior-year comparatives: four sources, one stored column.

The database role is findraft. Golden current figures stay put.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.services.org_provisioning import provision_first_signup
from app.services.prior_year import (
    FACE_DATE_NOTICE,
    FILED_ACCOUNTS,
    FIRST_PERIOD_STATEMENT,
    MANUAL_BLOCKED,
    MAPPING_CONFIRM,
    STALE_NOTICE,
    UNDO_CLOSED,
    manual_column_message,
)
from app.services.render_jobs import payload_from_composed
from app.services.statutory_compose import compose_pdf_parts
from app.services.statutory_docx import build_docx
from findraft.engine.reconciliation import check_prior_year_gate
from findraft.models.draft_version import DraftVersion
from tests.conftest import auth_headers, make_access_token
from tests.test_adopted_trial_balance import _insert_tb
from tests.test_organisations_api import _add_org_user
from tests.test_statutory_statements import _golden

_FORBIDDEN = "You don't have permission to access this resource."
_FINAL = "This draft is final. It cannot be changed."
_LOCKED = "This draft is locked. It cannot be changed."
_FROZEN = "This draft is frozen. It cannot be changed."


def _print_role() -> None:
    with SyncSessionLocal() as session:
        role = session.execute(text("SELECT current_user")).scalar_one()
    assert role == "findraft"


def _manual_body(*pairs: tuple[str, str]) -> dict[str, object]:
    return {
        "matches_filed_accounts": True,
        "lines": [{"canonical_line": name, "amount": amount} for name, amount in pairs],
    }


async def _open_year(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
    *,
    start: str = "2026-01-01",
    end: str = "2026-12-31",
) -> tuple[str, dict[str, str], uuid.UUID]:
    headers = auth_headers(provisioned_org["token"])
    created = await api_client.post(
        f"/clients/{provisioned_org['client_id']}/companies",
        headers=headers,
        json={"name": f"Harbour {end}"},
    )
    assert created.status_code == 201, created.text
    company_id = uuid.UUID(created.json()["id"])
    opened = await api_client.post(
        "/year-ends",
        headers=headers,
        json={
            "company_id": str(company_id),
            "period_start": start,
            "period_end": end,
        },
    )
    assert opened.status_code == 201, opened.text
    return opened.json()["id"], headers, company_id


def _draft(
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    year_end_id: str,
    pack_id: str,
    pack_version: str,
    status: str = "draft",
    frozen: bool = False,
    version_number: int = 1,
    snapshot: dict[str, object] | None = None,
    frozen_inputs: dict[str, object] | None = None,
) -> uuid.UUID:
    draft_id = uuid.uuid4()
    stored_snapshot = snapshot
    inputs_sha: str | None = None
    engine_sha: str | None = None
    if status == "final":
        stored_snapshot = (
            snapshot if snapshot is not None else {"canonical_current": {}}
        )
        inputs_sha = "a" * 64
        engine_sha = "b" * 64
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            DraftVersion(
                id=draft_id,
                org_id=org_id,
                company_id=company_id,
                year_end_id=uuid.UUID(year_end_id),
                version_number=version_number,
                pack_id=pack_id,
                pack_version=pack_version,
                status=status,
                is_frozen=frozen,
                snapshot=stored_snapshot,
                frozen_inputs=frozen_inputs,
                inputs_sha256=inputs_sha,
                engine_sha=engine_sha,
            )
        )
        session.commit()
    return draft_id


async def _pack(
    api_client: AsyncClient, headers: dict[str, str], year_end_id: str
) -> tuple[str, str]:
    loaded = await api_client.get(f"/year-ends/{year_end_id}", headers=headers)
    assert loaded.status_code == 200, loaded.text
    body = loaded.json()
    return str(body["pack_id"]), str(body["pack_version"])


def test_manual_checks_refuse_an_unbalanced_column_and_keep_a_balanced_one() -> None:
    _print_role()
    cash = {"CASH": Decimal("10.00")}
    assert manual_column_message(cash) is not None
    assert "Assets" in (manual_column_message(cash) or "")
    plant = {
        "FA_PLANT_COST": Decimal("100.00"),
        "RETAINED_EARNINGS": Decimal("-100.00"),
    }
    assert manual_column_message(plant) is not None
    assert "FA roll-forward" in (manual_column_message(plant) or "")
    reserve = {
        "CASH": Decimal("150.00"),
        "RETAINED_EARNINGS": Decimal("-50.00"),
        "REVENUE": Decimal("-100.00"),
    }
    rolled = manual_column_message(reserve)
    assert rolled is not None
    assert rolled.startswith("RE:")
    balanced = {
        "CASH": Decimal("322062.00"),
        "RETAINED_EARNINGS": Decimal("-322062.00"),
    }
    assert manual_column_message(balanced) is None


def test_a_confirmed_column_keeps_the_golden_current_figures(tmp_path: Path) -> None:
    current = _golden()
    assert current.net_assets == Decimal("455812.00")
    assert current.profit == Decimal("157650.00")
    assert current.html is not None
    assert "2025 €" in current.html
    assert "2024 €" in current.html
    assert FIRST_PERIOD_STATEMENT not in current.html
    first = _golden(first_financial_period=True)
    assert first.net_assets == Decimal("455812.00")
    assert first.profit == Decimal("157650.00")
    assert first.html is not None
    assert "Comparative amounts are not presented." in first.html
    assert "first financial period" in first.html
    assert "2024 €" not in first.html
    html, sections = compose_pdf_parts(
        current,
        report_setup=None,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        first_financial_period=False,
        currency="GBP",
    )
    assert "2024 £" in html
    assert "2025 £" in html
    dest = tmp_path / "comparatives.docx"
    build_docx(
        payload_from_composed(
            watermark="DRAFT",
            company_name="Harbour Limited",
            sections=sections,
        ),
        dest,
    )
    with ZipFile(dest) as archive:
        xml = archive.read("word/document.xml").decode()
    assert "2024" in xml
    assert "2025" in xml
    engine = Path(__file__).resolve().parents[2] / "findraft" / "engine"
    for path in engine.rglob("*.py"):
        assert "report_setup" not in path.read_text()


def test_gate_fix_points_at_the_prior_year_page() -> None:
    from app.services.dashboard_groups import present_check

    fix = present_check("V-GATE-001").fix
    assert fix.section == "prior-year"
    assert fix.anchor is None
    blocked = check_prior_year_gate(False)
    assert blocked is not None
    assert blocked.message.startswith("This draft needs comparative figures.")


@pytest.mark.asyncio
async def test_manual_entry_stores_only_a_confirmed_balanced_column(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    _print_role()
    year_end_id, headers, _company = await _open_year(api_client, provisioned_org)
    missing = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json={"lines": [{"canonical_line": "CASH", "amount": "10.00"}]},
    )
    assert missing.status_code == 422, missing.text
    assert missing.json()["detail"] == FILED_ACCOUNTS
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json={
            "matches_filed_accounts": False,
            "lines": [
                {"canonical_line": "CASH", "amount": "10.00"},
                {"canonical_line": "SHARE_CAPITAL", "amount": "-10.00"},
            ],
        },
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == FILED_ACCOUNTS
    unbalanced = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json=_manual_body(("CASH", "10.00")),
    )
    assert unbalanced.status_code == 422, unbalanced.text
    assert "Assets" in unbalanced.json()["detail"]
    plant = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json=_manual_body(
            ("FA_PLANT_COST", "100.00"), ("RETAINED_EARNINGS", "-100.00")
        ),
    )
    assert plant.status_code == 422, plant.text
    assert "FA roll-forward" in plant.json()["detail"]
    reserve = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json=_manual_body(
            ("CASH", "150.00"),
            ("RETAINED_EARNINGS", "-50.00"),
            ("REVENUE", "-100.00"),
        ),
    )
    assert reserve.status_code == 422, reserve.text
    assert reserve.json()["detail"].startswith("RE:")
    stored = await api_client.get(
        f"/year-ends/{year_end_id}/prior-year", headers=headers
    )
    assert stored.status_code == 200, stored.text
    assert stored.json()["prior_year_validated"] is False
    assert stored.json()["stored_lines"] == []
    saved = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json=_manual_body(("CASH", "10.00"), ("SHARE_CAPITAL", "-10.00")),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["comparative_source"] == "manual"
    assert saved.json()["prior_year_validated"] is True


@pytest.mark.asyncio
async def test_first_period_undo_and_a_closed_draft(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    _print_role()
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    year_end_id, headers, company_id = await _open_year(api_client, provisioned_org)
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                """
                INSERT INTO findraft_year_ends (
                  id, org_id, company_id, period_start, period_end,
                  pack_id, pack_version
                )
                SELECT :id, org_id, company_id, DATE '2024-01-01', DATE '2024-12-31',
                       pack_id, pack_version
                FROM findraft_year_ends WHERE id = :current
                """
            ),
            {"id": str(uuid.uuid4()), "current": year_end_id},
        )
        session.commit()
    blocked = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert blocked.status_code == 409, blocked.text
    assert "2024-12-31" in blocked.json()["detail"]
    alone_id, alone_headers, alone_company = await _open_year(
        api_client,
        provisioned_org,
        start="2027-01-01",
        end="2027-12-31",
    )
    marked = await api_client.post(
        f"/year-ends/{alone_id}/first-financial-period",
        headers=alone_headers,
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["first_financial_period"] is True
    assert marked.json()["prior_year_validated"] is True
    undone = await api_client.post(
        f"/year-ends/{alone_id}/first-financial-period/undo",
        headers=alone_headers,
    )
    assert undone.status_code == 200, undone.text
    assert undone.json()["first_financial_period"] is False
    assert undone.json()["prior_year_validated"] is False
    gate = await api_client.get(
        f"/year-ends/{alone_id}/reconciliation-gate",
        headers=alone_headers,
    )
    assert gate.json()["open"] is False
    assert gate.json()["code"] == "V-GATE-001"
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        count = session.execute(
            text(
                "SELECT count(*) FROM findraft_prior_year_lines "
                "WHERE year_end_id = :year_end"
            ),
            {"year_end": alone_id},
        ).scalar_one()
        audit = session.execute(
            text(
                """
                SELECT new_value FROM audit_logs
                WHERE org_id = :org AND action = 'first_financial_period_cleared'
                  AND entity_id = :year_end
                """
            ),
            {"org": str(org_id), "year_end": alone_id},
        ).one()
    assert int(count) == 0
    assert audit.new_value == {"year_end_id": alone_id}
    marked_again = await api_client.post(
        f"/year-ends/{alone_id}/first-financial-period",
        headers=alone_headers,
    )
    assert marked_again.status_code == 200, marked_again.text
    pack_id, pack_version = await _pack(api_client, alone_headers, alone_id)
    _draft(
        org_id=org_id,
        company_id=alone_company,
        year_end_id=alone_id,
        pack_id=pack_id,
        pack_version=pack_version,
        status="final",
    )
    closed = await api_client.post(
        f"/year-ends/{alone_id}/first-financial-period/undo",
        headers=alone_headers,
    )
    assert closed.status_code == 409, closed.text
    assert closed.json()["detail"] == UNDO_CLOSED
    still = await api_client.get(f"/year-ends/{alone_id}", headers=alone_headers)
    assert still.json()["first_financial_period"] is True
    assert still.json()["prior_year_validated"] is True
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        cleared = session.execute(
            text(
                """
                SELECT count(*) FROM audit_logs
                WHERE org_id = :org AND action = 'first_financial_period_cleared'
                  AND entity_id = :year_end
                """
            ),
            {"org": str(org_id), "year_end": alone_id},
        ).scalar_one()
    assert int(cleared) == 1


@pytest.mark.asyncio
async def test_prior_trial_balance_snapshot_differences_and_stale_notice(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    _print_role()
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    year_end_id, headers, company_id = await _open_year(api_client, provisioned_org)
    rows = (
        ("1000", "Bank", "80.00", "0.00", "80.00", "cash"),
        ("3100", "Retained earnings", "0.00", "80.00", "-80.00", "retained_earnings"),
    )
    tb_id = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=rows,
        period_end=date(2025, 12, 31),
        period_start=date(2025, 1, 1),
    )
    gap = (
        ("1000", "Bank", "80.00", "0.00", "80.00", "cash"),
        ("6000", "Office costs", "10.00", "0.00", "10.00", "operating_expenses"),
        ("3100", "Retained earnings", "0.00", "90.00", "-90.00", "retained_earnings"),
    )
    # A second company keeps the gap trial balance off this year end's source.
    preview = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year/from-trial-balance",
        headers=headers,
        json={"confirm": False},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["prior_year_validated"] is False
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        audits = session.execute(
            text(
                "SELECT count(*) FROM audit_logs "
                "WHERE org_id = :org AND action = 'prior_year_confirmed'"
            ),
            {"org": str(org_id)},
        ).scalar_one()
    assert int(audits) == 0
    confirmed = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year/from-trial-balance",
        headers=headers,
        json={"confirm": True},
    )
    assert confirmed.status_code == 200, confirmed.text
    stored = {
        line["canonical_line"]: line["amount"]
        for line in confirmed.json()["stored_lines"]
    }
    assert stored["CASH"] == "80.00"
    assert stored["RETAINED_EARNINGS"] == "-80.00"
    assert confirmed.json()["comparative_source"] == "product1_tb"
    setup = await api_client.get(
        f"/year-ends/{year_end_id}/report-setup", headers=headers
    )
    assert setup.status_code == 200, setup.text
    assert setup.json()["face_dates"]["prior_start"] == "2025-01-01"
    assert setup.json()["face_dates"]["prior_end"] == "2025-12-31"
    manual = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=headers,
        json=_manual_body(("CASH", "10.00"), ("SHARE_CAPITAL", "-10.00")),
    )
    assert manual.status_code == 422, manual.text
    assert manual.json()["detail"] == MANUAL_BLOCKED
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                "UPDATE trial_balances SET parsed_data = "
                "jsonb_set(parsed_data, '{rows,0,debit}', '\"81.00\"') "
                "WHERE id = :id"
            ),
            {"id": str(tb_id)},
        )
        session.commit()
    stale = await api_client.get(
        f"/year-ends/{year_end_id}/prior-year", headers=headers
    )
    assert stale.json()["stale_notice"] == STALE_NOTICE
    assert {
        line["canonical_line"]: line["amount"] for line in stale.json()["stored_lines"]
    }["CASH"] == "80.00"
    del gap


@pytest.mark.asyncio
async def test_mapping_differences_must_be_confirmed(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    _print_role()
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    year_end_id, headers, company_id = await _open_year(
        api_client, provisioned_org, start="2026-01-01", end="2026-12-31"
    )
    rows = (
        ("1000", "Bank", "40.00", "0.00", "40.00", "cash"),
        ("2100", "Trade debtors", "60.00", "0.00", "60.00", "trade_receivables"),
        ("3100", "Retained earnings", "0.00", "100.00", "-100.00", "retained_earnings"),
    )
    _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=rows,
        period_end=date(2025, 12, 31),
        period_start=date(2025, 1, 1),
    )
    pack_id, pack_version = await _pack(api_client, headers, year_end_id)
    # Statements for the previous period live on a year end for this company.
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        previous = session.execute(
            text(
                """
                INSERT INTO findraft_year_ends (
                  id, org_id, company_id, period_start, period_end,
                  pack_id, pack_version
                )
                SELECT :id, org_id, company_id, DATE '2025-01-01', DATE '2025-12-31',
                       pack_id, pack_version
                FROM findraft_year_ends WHERE id = :current
                RETURNING id
                """
            ),
            {"id": str(uuid.uuid4()), "current": year_end_id},
        ).scalar_one()
        session.commit()
    _draft(
        org_id=org_id,
        company_id=company_id,
        year_end_id=str(previous),
        pack_id=pack_id,
        pack_version=pack_version,
        status="final",
        frozen_inputs={
            "tb_lines": [
                {
                    "nominal_code": "1000",
                    "account_name": "Bank",
                    "debit": "40.00",
                    "credit": "0.00",
                },
                {
                    "nominal_code": "2100",
                    "account_name": "Trade debtors",
                    "debit": "60.00",
                    "credit": "0.00",
                },
                {
                    "nominal_code": "3100",
                    "account_name": "Retained earnings",
                    "debit": "0.00",
                    "credit": "100.00",
                },
            ],
            "mappings": {
                "1000": "TRADE_DEBTORS",
                "2100": "TRADE_DEBTORS",
                "3100": "RETAINED_EARNINGS",
            },
            "prior_canonical": {},
            "prior_retained_earnings": "0.00",
        },
        snapshot={"canonical_current": {"CASH": "1.00"}},
    )
    page = await api_client.get(f"/year-ends/{year_end_id}/prior-year", headers=headers)
    assert page.status_code == 200, page.text
    source = next(
        item for item in page.json()["sources"] if item["kind"] == "product1_tb"
    )
    listed = source["mapping_differences"]
    assert listed == [
        {
            "account_code": "1000",
            "account_name": "Bank",
            "previous_line": "TRADE_DEBTORS",
            "current_line": "CASH",
        }
    ]
    assert "40.00" not in str(listed)
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year/from-trial-balance",
        headers=headers,
        json={"confirm": True},
    )
    assert refused.status_code == 422, refused.text
    body = refused.json()["detail"]
    assert body["message"] == MAPPING_CONFIRM
    assert body["mapping_differences"] == listed
    quiet = await api_client.get(
        f"/year-ends/{year_end_id}/prior-year", headers=headers
    )
    assert quiet.json()["prior_year_validated"] is False
    saved = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year/from-trial-balance",
        headers=headers,
        json={"confirm": True, "mapping_differences_confirmed": True},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["prior_year_validated"] is True


@pytest.mark.asyncio
async def test_unmapped_and_non_contiguous_trial_balances_store_nothing(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    year_end_id, headers, company_id = await _open_year(api_client, provisioned_org)
    _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(("1000", "Bank", "10.00", "0.00", "10.00", "cash"),),
        period_end=date(2025, 12, 31),
        confirmed=False,
    )
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year/from-trial-balance",
        headers=headers,
        json={"confirm": True},
    )
    assert refused.status_code == 422, refused.text
    assert "is not confirmed" in refused.json()["detail"]
    page = await api_client.get(f"/year-ends/{year_end_id}/prior-year", headers=headers)
    assert page.json()["prior_year_validated"] is False
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text("UPDATE trial_balances SET is_deleted = true WHERE company_id = :id"),
            {"id": str(company_id)},
        )
        session.execute(
            text("DELETE FROM account_mappings WHERE company_id = :id"),
            {"id": str(company_id)},
        )
        session.commit()
    _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(
            ("6000", "Office costs", "10.00", "0.00", "10.00", "operating_expenses"),
        ),
        period_end=date(2025, 12, 31),
        confirm_sublines=False,
    )
    missing = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year/from-trial-balance",
        headers=headers,
        json={"confirm": True},
    )
    assert missing.status_code == 422, missing.text
    assert "needs a statutory sub-line" in missing.json()["detail"]
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text("UPDATE trial_balances SET is_deleted = true WHERE company_id = :id"),
            {"id": str(company_id)},
        )
        session.execute(
            text("DELETE FROM account_mappings WHERE company_id = :id"),
            {"id": str(company_id)},
        )
        session.commit()
    _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(("1000", "Bank", "10.00", "0.00", "10.00", "not_a_line"),),
        period_end=date(2025, 12, 31),
    )
    home = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year/from-trial-balance",
        headers=headers,
        json={"confirm": True},
    )
    assert home.status_code == 422, home.text
    assert "no single statutory line" in home.json()["detail"]
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text("UPDATE trial_balances SET is_deleted = true WHERE company_id = :id"),
            {"id": str(company_id)},
        )
        session.execute(
            text("DELETE FROM account_mappings WHERE company_id = :id"),
            {"id": str(company_id)},
        )
        session.commit()
    _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(("1000", "Bank", "10.00", "0.00", "10.00", "cash"),),
        period_end=date(2025, 6, 30),
        period_start=date(2025, 1, 1),
    )
    gap = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year/from-trial-balance",
        headers=headers,
        json={"confirm": True},
    )
    assert gap.status_code == 422, gap.text
    assert gap.json()["detail"] == (
        "This trial balance ends on 2025-06-30. "
        "This period starts on 2026-01-01. "
        "The prior period must end the day before."
    )
    still = await api_client.get(
        f"/year-ends/{year_end_id}/prior-year", headers=headers
    )
    assert still.json()["prior_year_validated"] is False
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text("UPDATE trial_balances SET is_deleted = true WHERE company_id = :id"),
            {"id": str(company_id)},
        )
        session.execute(
            text("DELETE FROM account_mappings WHERE company_id = :id"),
            {"id": str(company_id)},
        )
        session.commit()
    _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(
            ("1000", "Bank", "10.00", "0.00", "10.00", "cash"),
            ("1000", "Petty cash", "5.00", "0.00", "5.00", "cash"),
        ),
        period_end=date(2025, 12, 31),
        period_start=date(2025, 1, 1),
    )
    duplicate = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year/from-trial-balance",
        headers=headers,
        json={"confirm": True},
    )
    assert duplicate.status_code == 422, duplicate.text
    assert duplicate.json()["detail"] == "Duplicate nominal code: 1000"
    quiet = await api_client.get(
        f"/year-ends/{year_end_id}/prior-year", headers=headers
    )
    assert quiet.json()["prior_year_validated"] is False


@pytest.mark.asyncio
async def test_final_snapshot_copy_does_not_change_the_final_row(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    year_end_id, headers, company_id = await _open_year(api_client, provisioned_org)
    pack_id, pack_version = await _pack(api_client, headers, year_end_id)
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        previous = session.execute(
            text(
                """
                INSERT INTO findraft_year_ends (
                  id, org_id, company_id, period_start, period_end,
                  pack_id, pack_version
                )
                SELECT :id, org_id, company_id, DATE '2025-01-01', DATE '2025-12-31',
                       pack_id, pack_version
                FROM findraft_year_ends WHERE id = :current
                RETURNING id
                """
            ),
            {"id": str(uuid.uuid4()), "current": year_end_id},
        ).scalar_one()
        session.commit()
    snapshot = {
        "canonical_current": {
            "CASH": "25.00",
            "RETAINED_EARNINGS": "-25.00",
        }
    }
    draft_id = _draft(
        org_id=org_id,
        company_id=company_id,
        year_end_id=str(previous),
        pack_id=pack_id,
        pack_version=pack_version,
        status="final",
        snapshot=snapshot,
    )
    dated = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json={
            "rounding": "unit",
            "statement_type": "draft",
            "face_dates": {
                "current_start": "2026-01-01",
                "current_end": "2026-12-31",
                "prior_start": "2019-01-01",
                "prior_end": "2019-12-31",
            },
            "column_headers": {
                "as_at_current": "2026 £",
                "as_at_prior": "2025 £",
                "ended_current": "2026 £",
                "ended_prior": "2025 £",
            },
        },
    )
    assert dated.status_code == 200, dated.text
    named = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year/from-final",
        headers=headers,
        json={"confirm": False},
    )
    assert named.status_code == 200, named.text
    assert named.json()["prior_year_validated"] is False
    source = next(
        item for item in named.json()["sources"] if item["kind"] == "final_snapshot"
    )
    assert source["draft_id"] == str(draft_id)
    copied = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year/from-final",
        headers=headers,
        json={"confirm": True},
    )
    assert copied.status_code == 200, copied.text
    stored = {
        line["canonical_line"]: line["amount"] for line in copied.json()["stored_lines"]
    }
    assert stored == {"CASH": "25.00", "RETAINED_EARNINGS": "-25.00"}
    assert copied.json()["face_date_notice"] == FACE_DATE_NOTICE
    kept_dates = await api_client.get(
        f"/year-ends/{year_end_id}/report-setup", headers=headers
    )
    assert kept_dates.json()["face_dates"]["prior_start"] == "2019-01-01"
    assert kept_dates.json()["face_dates"]["prior_end"] == "2019-12-31"
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        kept = session.execute(
            text("SELECT snapshot FROM findraft_draft_versions WHERE id = :id"),
            {"id": str(draft_id)},
        ).scalar_one()
    assert kept["canonical_current"] == snapshot["canonical_current"]


@pytest.mark.asyncio
async def test_viewer_is_forbidden_and_another_organisation_is_hidden(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    year_end_id, headers, _company = await _open_year(api_client, provisioned_org)
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    _viewer, _clerk, viewer_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="viewer",
        email_prefix="prior-viewer",
    )
    viewer = auth_headers(viewer_token)
    for path, body in (
        ("/prior-year", _manual_body(("CASH", "10.00"), ("SHARE_CAPITAL", "-10.00"))),
        ("/prior-year/from-trial-balance", {"confirm": True}),
        ("/prior-year/from-final", {"confirm": True}),
        ("/first-financial-period", None),
        ("/first-financial-period/undo", None),
    ):
        refused = await api_client.post(
            f"/year-ends/{year_end_id}{path}",
            headers=viewer,
            json=body,
        )
        assert refused.status_code == 403, refused.text
        assert refused.json()["detail"] == _FORBIDDEN
    readable = await api_client.get(
        f"/year-ends/{year_end_id}/prior-year", headers=viewer
    )
    assert readable.status_code == 200, readable.text
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_prior_{suffix}"
    clerk_user_id = f"user_prior_{suffix}"
    with SyncSessionLocal() as session:
        other = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name="Other practice",
            clerk_user_id=clerk_user_id,
            email=f"prior-{suffix}@example.com",
        )
        session.commit()
        other_org_id = other.organisation.id
    token_b = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        org_uuid=other_org_id,
    )
    hidden = await api_client.post(
        f"/year-ends/{year_end_id}/prior-year",
        headers=auth_headers(token_b),
        json=_manual_body(("CASH", "10.00"), ("SHARE_CAPITAL", "-10.00")),
    )
    assert hidden.status_code == 404, hidden.text
    closed_year, closed_headers, closed_company = await _open_year(
        api_client, provisioned_org, start="2028-01-01", end="2028-12-31"
    )
    pack_id, pack_version = await _pack(api_client, closed_headers, closed_year)
    for version, status, frozen, detail in (
        (1, "final", False, _FINAL),
        (2, "locked", False, _LOCKED),
        (3, "draft", True, _FROZEN),
    ):
        _draft(
            org_id=org_id,
            company_id=closed_company,
            year_end_id=closed_year,
            pack_id=pack_id,
            pack_version=pack_version,
            status=status,
            frozen=frozen,
            version_number=version,
        )
        refused = await api_client.post(
            f"/year-ends/{closed_year}/prior-year",
            headers=closed_headers,
            json=_manual_body(("CASH", "10.00"), ("SHARE_CAPITAL", "-10.00")),
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["detail"] == detail
    del headers


def test_open_draft_trigger_migration_has_no_grant_all() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "z2a3b4c5d6_prior_year_open_draft.py"
    ).read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "z2a3b4c5d6"' in source
    assert 'down_revision: Union[str, None] = "y1z2a3b4c5"' in source
    assert "GRANT ALL" not in executable
    assert "findraft_year_ends_prior_locked" in source
    assert "findraft_prior_year_lines_locked" in source
    assert FACE_DATE_NOTICE
