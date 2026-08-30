"""Organisations API tests — settings, billing-field exclusion, role gates."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.user import User
from app.services.org_provisioning import user_id_for_clerk_user
from tests.conftest import auth_headers, make_access_token


def _add_org_user(
    *,
    org_id: uuid.UUID,
    clerk_org_id: str,
    role: str,
    email_prefix: str,
) -> tuple[uuid.UUID, str, str]:
    """Insert a user into an existing org under RLS; return (user_id, clerk_user_id, token)."""
    suffix = uuid.uuid4().hex[:10]
    clerk_user_id = f"user_{role}_{suffix}"
    user_id = user_id_for_clerk_user(clerk_user_id)
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            User(
                id=user_id,
                clerk_user_id=clerk_user_id,
                org_id=org_id,
                email=f"{email_prefix}-{suffix}@example.com",
                role=role,
            )
        )
        session.commit()
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        role=role,
        org_uuid=org_id,
    )
    return user_id, clerk_user_id, token


@pytest.mark.asyncio
async def test_get_and_update_own_organisation(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    got = await api_client.get("/organisations/me", headers=headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["id"] == str(provisioned_org["org_id"])
    assert "subscription_tier" in body
    assert "subscription_status" in body
    assert body["functional_currency"] == "GBP"

    updated = await api_client.put(
        "/organisations/me",
        headers=headers,
        json={"name": "Renamed Walkthrough Org", "functional_currency": "eur"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Renamed Walkthrough Org"
    assert updated.json()["functional_currency"] == "EUR"


@pytest.mark.asyncio
async def test_put_subscription_tier_is_ignored_not_applied(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    before = (await api_client.get("/organisations/me", headers=headers)).json()
    assert before["subscription_tier"] == "free"

    response = await api_client.put(
        "/organisations/me",
        headers=headers,
        json={
            "name": before["name"],
            "subscription_tier": "scale",
            "subscription_status": "cancelled",
        },
    )
    # Must not 422 (erroring) and must not apply billing fields.
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["subscription_tier"] == "free"
    assert body["subscription_status"] == "active"
    assert body["subscription_tier"] != "scale"


@pytest.mark.asyncio
async def test_list_members(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="memberlist",
    )
    response = await api_client.get("/organisations/me/members", headers=headers)
    assert response.status_code == 200, response.text
    members = response.json()["members"]
    assert len(members) >= 2
    roles = {member["role"] for member in members}
    assert "owner" in roles
    assert "member" in roles


@pytest.mark.asyncio
async def test_invite_owner_succeeds_stub_member_forbidden(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    owner_headers = auth_headers(provisioned_org["token"])
    owner_invite = await api_client.post(
        "/organisations/me/invites",
        headers=owner_headers,
        json={"email": "newhire@example.com", "role": "member"},
    )
    assert owner_invite.status_code == 201, owner_invite.text
    stub = owner_invite.json()
    assert stub["status"] == "stub_pending_schema"
    assert stub["email"] == "newhire@example.com"
    assert "No invites table" in stub["detail"]

    _, _, member_token = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="invitemember",
    )
    member_headers = auth_headers(member_token)
    forbidden = await api_client.post(
        "/organisations/me/invites",
        headers=member_headers,
        json={"email": "blocked@example.com", "role": "viewer"},
    )
    assert forbidden.status_code == 403
    assert forbidden.status_code != 404


@pytest.mark.asyncio
async def test_remove_member_role_gated_and_last_owner_blocked(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    org_id = provisioned_org["org_id"]
    clerk_org_id = provisioned_org["clerk_org_id"]
    owner_headers = auth_headers(provisioned_org["token"])
    owner_user_id = provisioned_org["user_id"]

    member_id, _, member_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=clerk_org_id,
        role="member",
        email_prefix="removable",
    )

    # Member cannot remove anyone.
    member_forbidden = await api_client.delete(
        f"/organisations/me/members/{owner_user_id}",
        headers=auth_headers(member_token),
    )
    assert member_forbidden.status_code == 403

    # Owner can remove a member.
    removed = await api_client.delete(
        f"/organisations/me/members/{member_id}",
        headers=owner_headers,
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["status"] == "removed"

    # Sole owner cannot remove themselves.
    last_owner = await api_client.delete(
        f"/organisations/me/members/{owner_user_id}",
        headers=owner_headers,
    )
    assert last_owner.status_code == 400, last_owner.text
    assert "only owner" in last_owner.json()["detail"].lower()

    # Owner still present.
    members = (
        await api_client.get("/organisations/me/members", headers=owner_headers)
    ).json()["members"]
    assert any(m["id"] == str(owner_user_id) and m["role"] == "owner" for m in members)
