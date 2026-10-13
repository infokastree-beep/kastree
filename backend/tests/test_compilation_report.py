"""Compilation date and signatory are read on the compilation report.

The columns already exist. This does not add a final-draft gate. A final
draft shows the snapshot, and a directors' report fact survives this save.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.schemas.company_details import CompanyDetailsResponse
from app.services.final_workspace import company_details_from_workspace
from app.services.statutory_pages import build_statutory_pages
from findraft.models.draft_version import DraftVersion
from tests.conftest import auth_headers
from tests.test_organisations_api import _add_org_user
from tests.test_statutory_statements import _golden, _row

_FORBIDDEN = "You don't have permission to access this resource."
_FINAL = "This draft is final. It cannot be changed."
_LOCKED = "This draft is locked. It cannot be changed."


def _print_role() -> None:
    with SyncSessionLocal() as session:
        role = session.execute(text("SELECT current_user")).scalar_one()
    print(f"executing_role={role}", flush=True)
    assert role == "findraft"


def _stored_details(**overrides: object) -> dict[str, object]:
    stored: dict[str, object] = {
        "country_of_incorporation": "IE",
        "registered_office": "1 Harbour Road",
        "business_address": None,
        "company_number": "123456",
        "incorporated_on": None,
        "principal_activity": "Software",
        "secretary": None,
        "average_employees": None,
        "directors": [],
        "advisers": [],
        "share_classes": [],
        "approval_date": None,
        "signing_directors": [],
    }
    stored.update(overrides)
    return stored


def test_an_older_snapshot_still_validates_and_a_stored_one_is_read() -> None:
    older = company_details_from_workspace({"company_details": _stored_details()})
    assert older is not None
    assert older.compilation_date is None
    assert older.compilation_signatory is None
    parsed = CompanyDetailsResponse.model_validate(_stored_details())
    assert parsed.compilation_date is None

    stored = company_details_from_workspace(
        {
            "company_details": _stored_details(
                compilation_date="2026-06-15",
                compilation_signatory="Snapshot Person",
                accounting_records_location="Snapshot Street",
            )
        }
    )
    assert stored is not None
    assert stored.compilation_date == date(2026, 6, 15)
    assert stored.compilation_signatory == "Snapshot Person"
    assert stored.accounting_records_location == "Snapshot Street"


def test_compilation_page_names_a_missing_or_recorded_date() -> None:
    missing = build_statutory_pages(
        company_name="Harbour Limited",
        practice_name="North Practice",
        period_end="2026-12-31",
        directors="Ada Lovelace",
        secretary="",
        principal_activity="Software",
        currency="EUR",
        profit=Decimal("1.00"),
        size_eligible=True,
    )[0]
    text = "\n".join(missing.paragraphs)
    assert "The compilation date has not been recorded." in text
    assert "The compilation signatory has not been recorded." in text

    recorded = build_statutory_pages(
        company_name="Harbour Limited",
        practice_name="North Practice",
        period_end="2026-12-31",
        directors="Ada Lovelace",
        secretary="",
        principal_activity="Software",
        currency="EUR",
        profit=Decimal("1.00"),
        size_eligible=True,
        compilation_date="2026-03-31",
        compilation_signatory="Pat Lee",
    )[0]
    recorded_text = "\n".join(recorded.paragraphs)
    assert "Compilation date: 31 March 2026." in recorded_text
    assert "Compilation signatory: Pat Lee." in recorded_text
    assert "£" not in recorded_text
    assert "€" not in recorded_text


def test_golden_figures_stay_put() -> None:
    document = _golden()
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert _row(document.sofp, "Profit and loss account").current == Decimal(
        "455712.00"
    )


def _set_draft(
    *,
    org_id: uuid.UUID,
    year_end_id: str,
    status: str,
    snapshot: dict[str, object] | None = None,
) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        updated = session.execute(
            text(
                """
                UPDATE findraft_draft_versions
                SET status = :status,
                    snapshot = CASE
                      WHEN :snapshot IS NULL THEN snapshot
                      ELSE CAST(:snapshot AS jsonb)
                    END,
                    inputs_sha256 = CASE
                      WHEN :status = 'final' THEN COALESCE(inputs_sha256, :sha)
                      ELSE inputs_sha256
                    END,
                    engine_sha = CASE
                      WHEN :status = 'final' THEN COALESCE(engine_sha, :sha)
                      ELSE engine_sha
                    END
                WHERE org_id = :org AND year_end_id = :year_end
                """
            ),
            {
                "status": status,
                "snapshot": None if snapshot is None else json.dumps(snapshot),
                "org": str(org_id),
                "year_end": year_end_id,
                "sha": "b" * 64,
            },
        )
        assert updated.rowcount == 1
        session.commit()


@pytest.mark.asyncio
async def test_a_member_saves_the_compilation_report_and_a_final_draft_shows_the_snapshot(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    _print_role()
    headers = auth_headers(provisioned_org["token"])
    created = await api_client.post(
        f"/clients/{provisioned_org['client_id']}/companies",
        headers=headers,
        json={"name": "Compilation Harbour Limited"},
    )
    assert created.status_code == 201, created.text
    company_id = created.json()["id"]
    opened = await api_client.post(
        "/year-ends",
        headers=headers,
        json={
            "company_id": company_id,
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
        },
    )
    assert opened.status_code == 201, opened.text
    year_end_id = opened.json()["id"]
    loaded = await api_client.get(f"/year-ends/{year_end_id}", headers=headers)
    assert loaded.status_code == 200, loaded.text
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            DraftVersion(
                org_id=org_id,
                company_id=uuid.UUID(company_id),
                year_end_id=uuid.UUID(year_end_id),
                version_number=1,
                pack_id=loaded.json()["pack_id"],
                pack_version=loaded.json()["pack_version"],
                status="draft",
                is_frozen=False,
            )
        )
        session.commit()

    member_id, _clerk, member_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="compilation-report-member",
    )
    member_headers = auth_headers(member_token)
    _viewer_id, _viewer_clerk, viewer_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="viewer",
        email_prefix="compilation-report-viewer",
    )
    report = {
        "accounting_records_location": "1 Harbour Street, Dublin",
        "interim_dividend": "0.00",
        "recommended_dividend": "0.00",
    }
    placed = await api_client.put(
        f"/year-ends/{year_end_id}/directors-report",
        headers=member_headers,
        json=report,
    )
    assert placed.status_code == 200, placed.text

    refused = await api_client.put(
        f"/year-ends/{year_end_id}/compilation-report",
        headers=auth_headers(viewer_token),
        json={"compilation_date": "2026-03-01", "compilation_signatory": "Pat Lee"},
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"] == _FORBIDDEN

    broken = await api_client.put(
        f"/year-ends/{year_end_id}/compilation-report",
        headers=member_headers,
        json={"compilation_date": "2026-03-01", "compilation_signatory": "Pat\nLee"},
    )
    assert broken.status_code == 400, broken.text

    saved = await api_client.put(
        f"/year-ends/{year_end_id}/compilation-report",
        headers=member_headers,
        json={"compilation_date": "2026-03-01", "compilation_signatory": "Pat Lee"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["compilation_date"] == "2026-03-01"
    assert saved.json()["compilation_signatory"] == "Pat Lee"
    assert saved.json()["accounting_records_location"] == "1 Harbour Street, Dublin"
    assert isinstance(member_id, uuid.UUID)

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.execute(
            text(
                """
                SELECT user_id::text, new_value
                FROM audit_logs
                WHERE org_id = :org AND action = 'compilation_report_saved'
                  AND entity_id = :year_end
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"org": str(org_id), "year_end": year_end_id},
        ).one()
    assert row.user_id == str(member_id)
    assert "amount" not in row.new_value
    assert row.new_value["compilation_signatory"] == "Pat Lee"
    assert "0.00" not in json.dumps(row.new_value)

    _set_draft(org_id=org_id, year_end_id=year_end_id, status="locked")
    locked = await api_client.put(
        f"/year-ends/{year_end_id}/compilation-report",
        headers=member_headers,
        json={"compilation_date": "2026-03-02", "compilation_signatory": "Pat Lee"},
    )
    assert locked.status_code == 409, locked.text
    assert locked.json()["detail"] == _LOCKED

    snapshot = {
        "workspace": {
            "company_details": _stored_details(
                compilation_date="2026-06-15",
                compilation_signatory="Snapshot Person",
                accounting_records_location="Snapshot Street",
                approval_date="2026-02-01",
                signing_directors=["Ada Lovelace"],
            )
        }
    }
    _set_draft(
        org_id=org_id,
        year_end_id=year_end_id,
        status="final",
        snapshot=snapshot,
    )
    final = await api_client.put(
        f"/year-ends/{year_end_id}/compilation-report",
        headers=member_headers,
        json={"compilation_date": "2026-03-02", "compilation_signatory": "Pat Lee"},
    )
    assert final.status_code == 409, final.text
    assert final.json()["detail"] == _FINAL

    shown = await api_client.get(
        f"/year-ends/{year_end_id}/company-details",
        headers=member_headers,
    )
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert body["compilation_date"] == "2026-06-15"
    assert body["compilation_signatory"] == "Snapshot Person"
    assert body["accounting_records_location"] == "Snapshot Street"
    assert body["approval_date"] == "2026-02-01"
    assert body["signing_directors"] == ["Ada Lovelace"]
