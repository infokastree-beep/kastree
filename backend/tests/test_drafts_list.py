"""Draft list: version number, status, locked or frozen.

The latest draft GET still returns one row. This list reads the same versions.
The database role is findraft.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.services.org_provisioning import provision_first_signup
from app.db import SyncSessionLocal
from tests.conftest import auth_headers, make_access_token
from tests.test_organisations_api import _add_org_user
from tests.test_prior_year_comparatives import _draft, _open_year, _pack, _print_role


@pytest.mark.asyncio
async def test_draft_list_names_every_version_and_hides_other_orgs(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    _print_role()
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    year_end_id, headers, company_id = await _open_year(api_client, provisioned_org)
    empty = await api_client.get(f"/year-ends/{year_end_id}/drafts", headers=headers)
    assert empty.status_code == 200, empty.text
    assert empty.json()["drafts"] == []
    pack_id, pack_version = await _pack(api_client, headers, year_end_id)
    first_id = _draft(
        org_id=org_id,
        company_id=company_id,
        year_end_id=year_end_id,
        pack_id=pack_id,
        pack_version=pack_version,
        status="final",
        version_number=1,
    )
    second_id = _draft(
        org_id=org_id,
        company_id=company_id,
        year_end_id=year_end_id,
        pack_id=pack_id,
        pack_version=pack_version,
        status="locked",
        version_number=2,
    )
    third_id = _draft(
        org_id=org_id,
        company_id=company_id,
        year_end_id=year_end_id,
        pack_id=pack_id,
        pack_version=pack_version,
        status="draft",
        frozen=True,
        version_number=3,
    )
    listed = await api_client.get(f"/year-ends/{year_end_id}/drafts", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["year_end_id"] == year_end_id
    assert body["drafts"] == [
        {
            "draft_id": str(first_id),
            "version_number": 1,
            "status": "final",
            "locked": False,
            "frozen": False,
        },
        {
            "draft_id": str(second_id),
            "version_number": 2,
            "status": "locked",
            "locked": True,
            "frozen": False,
        },
        {
            "draft_id": str(third_id),
            "version_number": 3,
            "status": "draft",
            "locked": False,
            "frozen": True,
        },
    ]
    assert "amount" not in listed.text
    assert "snapshot" not in listed.text
    _viewer, _clerk, viewer_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="viewer",
        email_prefix="draft-list-viewer",
    )
    readable = await api_client.get(
        f"/year-ends/{year_end_id}/drafts",
        headers=auth_headers(viewer_token),
    )
    assert readable.status_code == 200, readable.text
    assert len(readable.json()["drafts"]) == 3
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_drafts_{suffix}"
    clerk_user_id = f"user_drafts_{suffix}"
    with SyncSessionLocal() as session:
        other = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name="Other practice",
            clerk_user_id=clerk_user_id,
            email=f"drafts-{suffix}@example.com",
        )
        session.commit()
        other_org_id = other.organisation.id
    hidden = await api_client.get(
        f"/year-ends/{year_end_id}/drafts",
        headers=auth_headers(
            make_access_token(
                clerk_user_id=clerk_user_id,
                clerk_org_id=clerk_org_id,
                org_uuid=other_org_id,
            )
        ),
    )
    assert hidden.status_code == 404, hidden.text
