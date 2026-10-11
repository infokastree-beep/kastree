"""Country of incorporation. Existing companies stay NULL. No figure change.

The column has no default. Ireland is a create-form preselect, not a server
default. On the Irish pack a missing country is a draft notice and blocks
FINAL. Any other country blocks the draft, finalise, PDF, and Word.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.company import Company
from app.services.company_details import (
    FOREIGN_PACK_MESSAGE,
    MISSING_INCORPORATION,
    blocks_final,
    company_detail_checks,
    incorporation_gate,
    incorporation_output_message,
)
from app.services.draft_workflow import _can_finalise
from findraft.models.year_end import YearEnd
from tests.conftest import auth_headers

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "l8m9n0o1p2_company_country_of_incorporation.py"
)
_IRISH = "frs102-1a-ie"
_NO_TB = "No confirmed trial balance is selected"
_NO_VERSION = "Trial balance version not found"
_NO_DRAFT = "Draft not found"


def test_migration_adds_a_nullable_column_and_resets_least_privilege() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert "ADD COLUMN country_of_incorporation VARCHAR(2)" in source
    assert "GRANT ALL" not in executable
    assert "SET DEFAULT" not in source
    assert "UPDATE companies" not in source.lower()
    assert "findraft_table_privileges.sql" in source


def test_column_has_no_default_and_an_omitted_insert_stays_null(
    provisioned_org: dict,
) -> None:
    with SyncSessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT is_nullable, column_default, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'companies'
                  AND column_name = 'country_of_incorporation'
                """
            )
        ).one()
        assert row.is_nullable == "YES"
        assert row.column_default is None
        assert row.character_maximum_length == 2

        set_rls_org_id(session, provisioned_org["org_id"])
        stored = session.execute(
            text(
                """
                INSERT INTO companies (id, client_id, org_id, name)
                VALUES (:id, :client_id, :org_id, :name)
                RETURNING country_of_incorporation
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "client_id": str(provisioned_org["client_id"]),
                "org_id": str(provisioned_org["org_id"]),
                "name": f"Omitted {uuid.uuid4().hex[:8]}",
            },
        ).scalar_one()
        assert stored is None
        session.rollback()

        set_rls_org_id(session, provisioned_org["org_id"])
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    """
                    INSERT INTO companies (
                      id, client_id, org_id, name, country_of_incorporation
                    )
                    VALUES (:id, :client_id, :org_id, :name, 'us')
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "client_id": str(provisioned_org["client_id"]),
                    "org_id": str(provisioned_org["org_id"]),
                    "name": f"Lower {uuid.uuid4().hex[:8]}",
                },
            )
            session.flush()
        session.rollback()


def _year_end(country: str | None, pack_id: str = _IRISH) -> tuple[Company, YearEnd]:
    company = Company(
        client_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        name="Northwind",
        functional_currency="EUR",
        country_of_incorporation=country,
    )
    year_end = YearEnd(
        org_id=company.org_id,
        company_id=uuid.uuid4(),
        period_end=date(2026, 12, 31),
        pack_id=pack_id,
        pack_version="2024.09",
    )
    return company, year_end


def _incorporation(company: Company, year_end: YearEnd) -> list:
    return [
        item
        for item in company_detail_checks(company, year_end)
        if item.code in {"V-CO-008", "V-CO-009"}
    ]


def test_null_is_a_notice_that_blocks_final_only() -> None:
    assert MISSING_INCORPORATION == "Country of incorporation not recorded"
    assert incorporation_gate(None, _IRISH) == "missing"
    assert incorporation_output_message(None, _IRISH, final=False) is None
    assert (
        incorporation_output_message(None, _IRISH, final=True) == MISSING_INCORPORATION
    )
    company, year_end = _year_end(None)
    notice = _incorporation(company, year_end)
    assert len(notice) == 1
    assert notice[0].code == "V-CO-008"
    assert notice[0].severity == "NOTICE"
    assert notice[0].passed is False
    assert notice[0].message == MISSING_INCORPORATION
    assert blocks_final(tuple(notice)) is True
    assert (
        _can_finalise("green", renderable=True, blocked=False, checks=tuple(notice))
        is False
    )


def test_ireland_adds_no_incorporation_check() -> None:
    assert incorporation_gate("IE", _IRISH) == "open"
    assert incorporation_gate("ie", _IRISH) == "open"
    assert incorporation_output_message("IE", _IRISH, final=True) is None
    company, year_end = _year_end("IE")
    assert _incorporation(company, year_end) == []
    assert _can_finalise("green", renderable=True, blocked=False, checks=()) is True


def test_another_country_blocks_every_irish_output() -> None:
    assert FOREIGN_PACK_MESSAGE == (
        "This pack is for a company incorporated in Ireland. "
        "No other country's pack is available."
    )
    assert incorporation_gate("US", _IRISH) == "foreign"
    assert (
        incorporation_output_message("US", _IRISH, final=False) == FOREIGN_PACK_MESSAGE
    )
    assert (
        incorporation_output_message("US", _IRISH, final=True) == FOREIGN_PACK_MESSAGE
    )
    company, year_end = _year_end("US")
    blocked = _incorporation(company, year_end)
    assert len(blocked) == 1
    assert blocked[0].code == "V-CO-009"
    assert blocked[0].severity == "BLOCKED"
    assert blocked[0].passed is False
    assert blocked[0].message == FOREIGN_PACK_MESSAGE
    assert blocks_final(tuple(blocked)) is True


def test_another_pack_does_not_apply_the_irish_country_gate() -> None:
    assert incorporation_gate(None, "other-pack") == "open"
    assert incorporation_gate("US", "other-pack") == "open"
    assert incorporation_output_message("US", "other-pack", final=True) is None
    company, year_end = _year_end("US", pack_id="other-pack")
    assert _incorporation(company, year_end) == []


async def _create_company(
    api_client: AsyncClient,
    provisioned_org: dict,
    *,
    name: str,
    country: str | None = None,
    include_country: bool = False,
) -> dict:
    body: dict[str, str | None] = {"name": name}
    if include_country:
        body["country_of_incorporation"] = country
    response = await api_client.post(
        f"/clients/{provisioned_org['client_id']}/companies",
        headers=auth_headers(provisioned_org["token"]),
        json=body,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _year_end_id(
    api_client: AsyncClient, provisioned_org: dict, company_id: str
) -> str:
    response = await api_client.post(
        "/year-ends",
        headers=auth_headers(provisioned_org["token"]),
        json={
            "company_id": company_id,
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["pack_id"] == _IRISH
    return str(response.json()["id"])


async def _call(
    api_client: AsyncClient,
    token: str,
    method: str,
    path: str,
    body: dict | None = None,
):
    headers = auth_headers(token)
    headers["Idempotency-Key"] = uuid.uuid4().hex
    if method == "GET":
        return await api_client.get(path, headers=headers)
    return await api_client.post(path, headers=headers, json=body)


@pytest.mark.asyncio
async def test_create_stores_null_unless_a_country_is_sent(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    practice = await api_client.put(
        "/organisations/me",
        headers=headers,
        json={"jurisdiction": "IE"},
    )
    assert practice.status_code == 200, practice.text
    assert practice.json()["jurisdiction"] == "IE"

    omitted = await _create_company(
        api_client, provisioned_org, name="No country sent"
    )
    assert omitted["country_of_incorporation"] is None
    assert omitted["functional_currency"] == "EUR"

    irish = await _create_company(
        api_client,
        provisioned_org,
        name="Sent Ireland",
        country="ie",
        include_country=True,
    )
    assert irish["country_of_incorporation"] == "IE"

    foreign = await _create_company(
        api_client,
        provisioned_org,
        name="Sent United States",
        country="US",
        include_country=True,
    )
    assert foreign["country_of_incorporation"] == "US"

    rejected = await api_client.post(
        f"/clients/{provisioned_org['client_id']}/companies",
        headers=headers,
        json={"name": "Too long", "country_of_incorporation": "Ireland"},
    )
    assert rejected.status_code == 422

    kept = await api_client.put(
        f"/companies/{irish['id']}",
        headers=headers,
        json={"name": "Sent Ireland"},
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["country_of_incorporation"] == "IE"

    cleared = await api_client.put(
        f"/companies/{irish['id']}",
        headers=headers,
        json={"country_of_incorporation": None},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["country_of_incorporation"] is None


@pytest.mark.asyncio
async def test_irish_pack_outputs_follow_the_recorded_country(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    token = provisioned_org["token"]
    missing = await _create_company(api_client, provisioned_org, name="Missing country")
    ireland = await _create_company(
        api_client,
        provisioned_org,
        name="Irish company",
        country="IE",
        include_country=True,
    )
    other = await _create_company(
        api_client,
        provisioned_org,
        name="US company",
        country="US",
        include_country=True,
    )
    cases = {
        "null": await _year_end_id(api_client, provisioned_org, missing["id"]),
        "IE": await _year_end_id(api_client, provisioned_org, ireland["id"]),
        "US": await _year_end_id(api_client, provisioned_org, other["id"]),
    }

    for label, year_end_id in cases.items():
        draft = uuid.uuid4()
        version = uuid.uuid4()
        calls = {
            "statements": (
                "GET",
                f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
                None,
            ),
            "pdf": (
                "GET",
                f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
                None,
            ),
            "version_statements": (
                "GET",
                f"/year-ends/{year_end_id}/trial-balance-versions/{version}/statements",
                None,
            ),
            "version_pdf": (
                "GET",
                f"/year-ends/{year_end_id}/trial-balance-versions/{version}/statements.pdf",
                None,
            ),
            "docx": (
                "POST",
                f"/year-ends/{year_end_id}/drafts/{draft}/document.docx",
                None,
            ),
            "finalise": (
                "POST",
                f"/year-ends/{year_end_id}/drafts/{draft}/finalise",
                {"row_version": 1},
            ),
        }
        for name, (method, path, body) in calls.items():
            response = await _call(api_client, token, method, path, body)
            detail = response.json()["detail"]
            if label == "US":
                assert response.status_code == 409, (label, name, response.text)
                assert detail == FOREIGN_PACK_MESSAGE
                continue
            if name == "finalise" and label == "null":
                assert response.status_code == 409, response.text
                assert detail == MISSING_INCORPORATION
                continue
            expected = {
                "statements": (404, _NO_TB),
                "pdf": (404, _NO_TB),
                "version_statements": (404, _NO_VERSION),
                "version_pdf": (404, _NO_VERSION),
                "docx": (404, _NO_DRAFT),
                "finalise": (404, _NO_DRAFT),
            }[name]
            assert (response.status_code, detail) == expected, (
                label,
                name,
                response.text,
            )
            assert detail not in {MISSING_INCORPORATION, FOREIGN_PACK_MESSAGE}
