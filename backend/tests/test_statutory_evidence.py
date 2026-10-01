"""Week 9 statutory evidence graph."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.main import app
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from app.services.statutory_evidence import build_evidence_lines
from app.services.statutory_statements import StatementRow, build_statutory_statements
from findraft.engine.schemas import TBLine
from tests.conftest import auth_headers, make_access_token
from tests.test_organisations_api import _add_org_user
from tests.test_reconciliation import _MAPPINGS, _TB, _TINY, _lines, _mapping_payload
from tests.test_role_enforcement import _set_role
from tests.test_statutory_statements import _entity, _golden, _import_csv, _ready_golden
from tests.test_tb_ingestion import _year_end

_NOT_READY = "Trial balance version is not ready"


@pytest.fixture
def stored_files(tmp_path: Path) -> Iterator[LocalPracticeStorage]:
    store = LocalPracticeStorage(tmp_path)
    app.dependency_overrides[get_source_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_source_storage, None)


def _by_label(lines: object, label: str) -> object:
    assert isinstance(lines, tuple)
    return next(line for line in lines if line.label == label)


def _sum_contributions(line: object) -> Decimal:
    accounts = line.accounts
    assert isinstance(accounts, tuple)
    return sum((account.contribution for account in accounts), Decimal("0"))


def test_golden_graph_ties_every_face_back_to_trial_balance_accounts() -> None:
    document = _golden()
    lines = build_evidence_lines(
        tb_lines=_lines(_TB),
        mappings=_MAPPINGS,
        sofp=document.sofp,
        income=document.income,
    )
    assert len(lines) == len(document.sofp) + len(document.income)
    face = {line.label: line.amount for line in lines}
    codes: list[str] = []
    for line in lines:
        component_total = sum((face[label] for label in line.components), Decimal("0"))
        assert _sum_contributions(line) + component_total == line.amount
        codes.extend(account.nominal_code for account in line.accounts)
    assert sorted(codes) == sorted(code for code, _name, _debit, _credit in _TB)
    tangible = _by_label(lines, "Tangible assets")
    assert tangible.amount == Decimal("134000.00")
    assert {account.nominal_code for account in tangible.accounts} == {
        "1500",
        "1501",
        "1505",
        "1506",
    }
    assert _sum_contributions(tangible) == Decimal("134000.00")
    dep = next(
        account for account in tangible.accounts if account.nominal_code == "1505"
    )
    assert dep.balance == Decimal("-52000.00")
    assert dep.contribution == Decimal("-52000.00")
    assert dep.presented_line == "FA_ACCUM_DEP"
    turnover = _by_label(lines, "Turnover")
    assert turnover.accounts[0].nominal_code == "4000"
    assert turnover.accounts[0].contribution == Decimal("2421300.00")
    retained = _by_label(lines, "Profit and loss account")
    assert retained.amount == Decimal("455712.00")
    assert retained.components == ("Profit for the financial year",)
    assert {account.nominal_code for account in retained.accounts} == {"3100", "8500"}
    dividend = next(
        account for account in retained.accounts if account.nominal_code == "8500"
    )
    assert dividend.contribution == Decimal("-24000.00")
    assert _by_label(lines, "Net assets").amount == Decimal("455812.00")
    assert _by_label(lines, "Total equity").amount == Decimal("455812.00")
    assert _by_label(lines, "Profit for the financial year").amount == Decimal(
        "157650.00"
    )
    assert _by_label(lines, "Stocks").amount == Decimal("0.00")
    assert _by_label(lines, "Stocks").accounts == ()


def test_sign_home_keeps_the_mapped_line_and_presents_the_home() -> None:
    rows = (
        TBLine("1200", "Bank current account", Decimal("0"), Decimal("40.00")),
        TBLine("2400", "Director's current account", Decimal("30.00"), Decimal("0")),
        TBLine("1500", "Plant", Decimal("110.00"), Decimal("0")),
        TBLine("3000", "Called up share capital", Decimal("0"), Decimal("100.00")),
    )
    mappings = {
        "1200": "CASH",
        "2400": "DIRECTOR_LOAN",
        "1500": "FA_PLANT_COST",
        "3000": "SHARE_CAPITAL",
    }
    document = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=list(rows),
        mappings=mappings,
        prior_retained_earnings=Decimal("0"),
        entity=_entity(),
    )
    assert document.renderable is True
    lines = build_evidence_lines(
        tb_lines=list(rows),
        mappings=mappings,
        sofp=document.sofp,
        income=document.income,
    )
    cash = _by_label(lines, "Cash at bank and in hand")
    assert cash.amount == Decimal("0.00")
    assert cash.accounts == ()
    creditors = _by_label(lines, "Creditors: amounts falling due within one year")
    bank = creditors.accounts[0]
    assert bank.nominal_code == "1200"
    assert bank.mapped_line == "CASH"
    assert bank.presented_line == "BANK_OVERDRAFT"
    assert bank.balance == Decimal("-40.00")
    assert bank.contribution == Decimal("-40.00")
    debtors = _by_label(lines, "Other debtors")
    director = debtors.accounts[0]
    assert director.mapped_line == "DIRECTOR_LOAN"
    assert director.presented_line == "OTHER_DEBTORS"
    assert director.contribution == Decimal("30.00")
    codes = [account.nominal_code for line in lines for account in line.accounts]
    assert sorted(codes) == ["1200", "1500", "2400", "3000"]


def test_a_face_that_does_not_tie_is_refused() -> None:
    document = _golden()
    tampered = tuple(
        StatementRow(label=row.label, current=Decimal("1.00"), prior=row.prior)
        if row.label == "Tangible assets"
        else row
        for row in document.sofp
    )
    with pytest.raises(ValueError, match="evidence does not tie: Tangible assets"):
        build_evidence_lines(
            tb_lines=_lines(_TB),
            mappings=_MAPPINGS,
            sofp=tampered,
            income=document.income,
        )
    invented = (StatementRow(label="Invented", current=Decimal("0.00"), prior=None),)
    with pytest.raises(
        ValueError, match="statement row has no evidence spec: Invented"
    ):
        build_evidence_lines(
            tb_lines=[],
            mappings={},
            sofp=invented,
            income=(),
        )


def _evidence_path(year_end_id: str, version_id: str) -> str:
    return f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/statements/evidence"


@pytest.mark.asyncio
async def test_api_golden_evidence_points_at_the_trial_balance_document(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    version_id = await _ready_golden(
        api_client, provisioned_org, stored_files, year_end_id
    )
    response = await api_client.get(
        _evidence_path(year_end_id, version_id),
        headers=auth_headers(provisioned_org["token"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["renderable"] is True
    assert body["build_error"] is None
    roles = {document["role"]: document for document in body["documents"]}
    assert set(roles) == {"trial_balance", "fixed_asset_register"}
    assert roles["trial_balance"]["filename"] == "golden.csv"
    assert roles["fixed_asset_register"]["filename"] == "fa.csv"
    register_id = roles["fixed_asset_register"]["id"]
    trial_id = roles["trial_balance"]["id"]
    codes: list[str] = []
    for line in body["lines"]:
        contributions = [
            Decimal(account["contribution"]) for account in line["accounts"]
        ]
        component_total = sum(
            (
                Decimal(other["amount"])
                for other in body["lines"]
                if other["label"] in line["components"]
            ),
            Decimal("0"),
        )
        assert sum(contributions, Decimal("0")) + component_total == Decimal(
            line["amount"]
        )
        for account in line["accounts"]:
            assert account["tb_line_id"]
            assert account["source_document_id"] == trial_id
            assert account["source_document_id"] != register_id
            codes.append(account["nominal_code"])
            assert Decimal(account["contribution"]) not in {
                Decimal("120000.00"),
                Decimal("30000.00"),
                Decimal("35600.00"),
            }
    assert sorted(codes) == sorted(code for code, _name, _debit, _credit in _TB)
    tangible = next(
        line for line in body["lines"] if line["label"] == "Tangible assets"
    )
    assert tangible["amount"] == "134000.00"
    retained = next(
        line for line in body["lines"] if line["label"] == "Profit and loss account"
    )
    assert retained["amount"] == "455712.00"
    assert retained["components"] == ["Profit for the financial year"]


@pytest.mark.asyncio
async def test_closed_gate_and_missing_register_withhold_or_link_honestly(
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
        file_key="evidence-gate-file",
        version_key="evidence-gate-version",
        process=False,
    )
    closed = await api_client.get(_evidence_path(year_end_id, pending), headers=headers)
    assert closed.status_code == 200, closed.text
    assert closed.json()["renderable"] is False
    assert closed.json()["blocked"] is True
    assert closed.json()["lines"] == []
    assert closed.json()["documents"] == []
    assert [item["code"] for item in closed.json()["checks"]] == ["V-GATE-001"]

    opened = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert opened.status_code == 200, opened.text
    still_pending = await api_client.get(
        _evidence_path(year_end_id, pending), headers=headers
    )
    assert still_pending.status_code == 400, still_pending.text
    assert still_pending.json()["detail"] == _NOT_READY

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
        file_key="evidence-plant-file",
        version_key="evidence-plant-version",
        process=True,
    )
    confirmed = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/mappings",
        headers=headers,
        json=_mapping_payload({"1500": "FA_PLANT_COST", "3000": "SHARE_CAPITAL"}),
    )
    assert confirmed.status_code == 200, confirmed.text
    report = await api_client.get(
        _evidence_path(year_end_id, version_id), headers=headers
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["renderable"] is True
    assert [document["role"] for document in body["documents"]] == ["trial_balance"]
    tangible = next(
        line for line in body["lines"] if line["label"] == "Tangible assets"
    )
    assert tangible["amount"] == "100.00"
    assert tangible["accounts"][0]["nominal_code"] == "1500"
    assert tangible["accounts"][0]["contribution"] == "100.00"
    assert tangible["accounts"][0]["source_document_id"] == body["documents"][0]["id"]


@pytest.mark.asyncio
async def test_viewer_can_read_evidence_and_another_year_end_is_hidden(
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
        file_key="evidence-viewer-file",
        version_key="evidence-viewer-version",
        process=False,
    )
    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="evidence-viewer",
    )
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="owner",
        org_uuid=provisioned_org["org_id"],
    )
    _set_role(org_id=provisioned_org["org_id"], user_id=user_id, role="viewer")
    readable = await api_client.get(
        _evidence_path(year_end_id, version_id),
        headers=auth_headers(token),
    )
    assert readable.status_code == 200, readable.text
    assert readable.json()["blocked"] is True
    headers = auth_headers(provisioned_org["token"])
    missing = await api_client.get(
        _evidence_path(str(uuid.uuid4()), str(uuid.uuid4())),
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
        _evidence_path(str(second.json()["id"]), version_id),
        headers=headers,
    )
    assert other.status_code == 404, other.text
