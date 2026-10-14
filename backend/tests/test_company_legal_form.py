"""Legal form is a listed code. Owners and admins record it. Members do not."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.schemas.company_details import CompanyDetailsResponse
from tests.conftest import auth_headers, make_access_token
from tests.test_organisations_api import _add_org_user


def _print_role() -> None:
    with SyncSessionLocal() as session:
        role = session.execute(text("SELECT current_user")).scalar_one()
    print(f"executing_role={role}", flush=True)
    assert role == "findraft"


def test_an_older_final_snapshot_still_validates_without_legal_form() -> None:
    stored = {
        "country_of_incorporation": "IE",
        "registered_office": "1 Harbour Road",
        "business_address": None,
        "company_number": "123456",
        "incorporated_on": None,
        "principal_activity": None,
        "secretary": None,
        "average_employees": None,
        "directors": [],
        "advisers": [],
        "share_classes": [],
        "approval_date": None,
        "signing_directors": [],
    }
    parsed = CompanyDetailsResponse.model_validate(stored)
    assert parsed.legal_form is None


@pytest.mark.asyncio
async def test_owner_records_a_legal_form_and_a_member_cannot_change_it(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    _print_role()
    headers = auth_headers(provisioned_org["token"])
    created = await api_client.post(
        f"/clients/{provisioned_org['client_id']}/companies",
        headers=headers,
        json={"name": "Harbour Trading"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["legal_form"] is None

    blank = await api_client.post(
        f"/clients/{provisioned_org['client_id']}/companies",
        headers=headers,
        json={"name": "Blank form", "legal_form": ""},
    )
    assert blank.status_code == 201, blank.text
    assert blank.json()["legal_form"] is None

    rejected = await api_client.post(
        f"/clients/{provisioned_org['client_id']}/companies",
        headers=headers,
        json={"name": "Free text", "legal_form": "limited company"},
    )
    assert rejected.status_code == 422

    company_id = created.json()["id"]
    saved = await api_client.put(
        f"/companies/{company_id}",
        headers=headers,
        json={"legal_form": "DAC"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["legal_form"] == "dac"

    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        row = session.execute(
            text(
                """
                SELECT user_id::text, old_value, new_value
                FROM audit_logs
                WHERE org_id = :org AND action = 'company_legal_form_set'
                  AND entity_id = :company
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"org": str(provisioned_org["org_id"]), "company": company_id},
        ).one()
    assert row.user_id == str(provisioned_org["user_id"])
    assert row.old_value == {"legal_form": None}
    assert row.new_value == {"legal_form": "dac"}
    recorded = json.dumps({"old": row.old_value, "new": row.new_value})
    assert "Harbour" not in recorded

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

    _member_id, _clerk_id, member_token = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="legal-form-member",
    )
    member_headers = auth_headers(member_token)
    same = await api_client.put(
        f"/year-ends/{year_end_id}/company-details",
        headers=member_headers,
        json={"legal_form": "dac", "registered_office": "1 Harbour Road, Dublin"},
    )
    assert same.status_code == 200, same.text
    assert same.json()["legal_form"] == "dac"
    assert same.json()["registered_office"] == "1 Harbour Road, Dublin"

    changed = await api_client.put(
        f"/year-ends/{year_end_id}/company-details",
        headers=member_headers,
        json={"legal_form": "ltd", "registered_office": "2 Other Road, Dublin"},
    )
    assert changed.status_code == 403, changed.text
    assert changed.json()["detail"] == (
        "Only an owner or an administrator can change the legal form."
    )
    kept = await api_client.get(
        f"/year-ends/{year_end_id}/company-details",
        headers=member_headers,
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["legal_form"] == "dac"
    assert kept.json()["registered_office"] == "1 Harbour Road, Dublin"

    admin_id, admin_clerk, _admin_token = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="admin",
        email_prefix="legal-form-admin",
    )
    admin_headers = auth_headers(
        make_access_token(
            clerk_user_id=admin_clerk,
            clerk_org_id=provisioned_org["clerk_org_id"],
            role="admin",
            org_uuid=provisioned_org["org_id"],
        )
    )
    assert isinstance(admin_id, uuid.UUID)
    admin_saved = await api_client.put(
        f"/year-ends/{year_end_id}/company-details",
        headers=admin_headers,
        json={"legal_form": "ltd", "registered_office": "1 Harbour Road, Dublin"},
    )
    assert admin_saved.status_code == 200, admin_saved.text
    assert admin_saved.json()["legal_form"] == "ltd"
