"""Start next year copies a final column and does not edit that draft.

The database role is findraft. Teardown must not leave it a DELETE grant
on archived_records.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.services.org_provisioning import provision_first_signup
from tests.conftest import auth_headers, make_access_token
from tests.test_organisations_api import _add_org_user
from tests.test_prior_year_comparatives import _draft, _open_year, _pack, _print_role


@pytest.mark.asyncio
async def test_start_next_year_asks_then_copies_the_final_column(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    _print_role()
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    year_end_id, headers, company_id = await _open_year(api_client, provisioned_org)
    pack_id, pack_version = await _pack(api_client, headers, year_end_id)
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/start-next-year",
        headers=headers,
        json={"confirm": False},
    )
    assert refused.status_code == 409, refused.text
    assert (
        refused.json()["detail"] == "This year end has no final draft to roll forward."
    )
    source_id = _draft(
        org_id=org_id,
        company_id=company_id,
        year_end_id=year_end_id,
        pack_id=pack_id,
        pack_version=pack_version,
        status="final",
        snapshot={
            "canonical_current": {
                "CASH": "10.00",
                "RETAINED_EARNINGS": "-10.00",
            }
        },
    )
    preview = await api_client.post(
        f"/year-ends/{year_end_id}/start-next-year",
        headers=headers,
        json={"confirm": False},
    )
    assert preview.status_code == 200, preview.text
    asked = preview.json()
    assert asked["period_start"] == "2027-01-01"
    assert asked["period_end"] == "2027-12-31"
    assert asked["source_draft_id"] == str(source_id)
    assert asked["year_end_id"] is None
    assert "comparative figures" in asked["carries_over"][0]
    assert "Adopt a trial balance" in asked["preparer_must"][0]
    assert "10.00" not in preview.text
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        started = session.execute(
            text(
                "SELECT count(*) FROM audit_logs "
                "WHERE org_id = :org AND action = 'next_year_started'"
            ),
            {"org": str(org_id)},
        ).scalar_one()
        existing = session.execute(
            text(
                "SELECT count(*) FROM findraft_year_ends "
                "WHERE company_id = :company AND period_end = '2027-12-31'"
            ),
            {"company": str(company_id)},
        ).scalar_one()
    assert int(started) == 0
    assert int(existing) == 0
    created = await api_client.post(
        f"/year-ends/{year_end_id}/start-next-year",
        headers=headers,
        json={"confirm": True},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["year_end_id"]
    assert "10.00" not in created.text
    nxt = body["year_end_id"]
    opened = await api_client.get(f"/year-ends/{nxt}/draft", headers=headers)
    assert opened.status_code == 200, opened.text
    assert opened.json()["status"] == "draft"
    column = await api_client.get(f"/year-ends/{nxt}/prior-year", headers=headers)
    assert column.status_code == 200, column.text
    stored = column.json()
    assert stored["comparative_source"] == "final_snapshot"
    assert stored["prior_year_validated"] is True
    amounts = {row["canonical_line"]: row["amount"] for row in stored["stored_lines"]}
    assert amounts["CASH"] == "10.00"
    assert amounts["RETAINED_EARNINGS"] == "-10.00"
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        audit = session.execute(
            text(
                """
                SELECT new_value FROM audit_logs
                WHERE org_id = :org AND action = 'next_year_started'
                """
            ),
            {"org": str(org_id)},
        ).one()
        snapshot = session.execute(
            text("SELECT snapshot FROM findraft_draft_versions WHERE id = :id"),
            {"id": str(source_id)},
        ).scalar_one()
    assert audit.new_value["source_draft_id"] == str(source_id)
    assert audit.new_value["next_year_end_id"] == nxt
    assert "10.00" not in str(audit.new_value)
    assert snapshot["canonical_current"]["CASH"] == "10.00"
    again = await api_client.post(
        f"/year-ends/{year_end_id}/start-next-year",
        headers=headers,
        json={"confirm": True},
    )
    assert again.status_code == 409, again.text
    assert "2027-12-31" in again.json()["detail"]
    _viewer, _clerk, viewer_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="viewer",
        email_prefix="next-year-viewer",
    )
    denied = await api_client.post(
        f"/year-ends/{year_end_id}/start-next-year",
        headers=auth_headers(viewer_token),
        json={"confirm": False},
    )
    assert denied.status_code == 403, denied.text
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_next_{suffix}"
    clerk_user_id = f"user_next_{suffix}"
    with SyncSessionLocal() as session:
        other = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name="Other practice",
            clerk_user_id=clerk_user_id,
            email=f"next-{suffix}@example.com",
        )
        session.commit()
        other_org_id = other.organisation.id
    hidden = await api_client.post(
        f"/year-ends/{year_end_id}/start-next-year",
        headers=auth_headers(
            make_access_token(
                clerk_user_id=clerk_user_id,
                clerk_org_id=clerk_org_id,
                org_uuid=other_org_id,
            )
        ),
        json={"confirm": True},
    )
    assert hidden.status_code == 404, hidden.text


def test_teardown_does_not_leave_findraft_delete_on_archived_records() -> None:
    """The parity login has no DELETE. The backend job's findraft is a superuser."""
    _print_role()
    with SyncSessionLocal() as session:
        superuser = session.execute(
            text(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = 'findraft'"
            )
        ).scalar_one()
        if superuser:
            pytest.skip(
                "This job's findraft login is a superuser. "
                "The parity job checks the grant."
            )
        allowed = session.execute(
            text(
                "SELECT has_table_privilege("
                "'findraft', 'archived_records', 'DELETE')"
            )
        ).scalar_one()
    assert allowed is False
