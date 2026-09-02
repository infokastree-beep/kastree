"""Owner-only admin overview API tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.db import SyncSessionLocal
from app.models.user import User
from app.models.waitlist_signup import WaitlistSignup
from tests.conftest import auth_headers
from tests.test_organisations_api import _add_org_user


@pytest.fixture
def platform_admin_allowlist(
    monkeypatch: pytest.MonkeyPatch,
    provisioned_org: dict,
) -> str:
    """Allow the provisioned org owner as a platform admin for positive admin tests."""
    with SyncSessionLocal() as session:
        email = session.scalar(
            select(User.email).where(User.id == provisioned_org["user_id"])
        )
    assert email
    monkeypatch.setattr(settings, "platform_admin_emails", email)
    return email


@pytest.mark.asyncio
async def test_admin_overview_owner_sees_platform_data(
    api_client: AsyncClient,
    provisioned_org: dict,
    platform_admin_allowlist: str,
) -> None:
    waitlist_email = f"admin-waitlist-{uuid.uuid4().hex[:8]}@example.com"
    with SyncSessionLocal() as session:
        session.add(
            WaitlistSignup(
                name="Waitlist Admin",
                email=waitlist_email,
                firm="Admin Firm",
                role="Partner",
            )
        )
        session.commit()

    headers = auth_headers(provisioned_org["token"])
    response = await api_client.get("/admin/overview", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["waitlist_count"] >= 1
    assert any(row["email"] == waitlist_email for row in body["waitlist_signups"])
    assert body["organisations_count"] >= 1
    assert body["users_count"] >= 1
    assert any(row["role"] == "owner" for row in body["users"])


@pytest.mark.asyncio
async def test_admin_overview_non_platform_owner_forbidden(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any org owner can reach /admin today without PLATFORM_ADMIN_EMAILS — must 403."""
    monkeypatch.setattr(settings, "platform_admin_emails", "founder-only@example.com")
    headers = auth_headers(provisioned_org["token"])
    response = await api_client.get("/admin/overview", headers=headers)
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_admin_overview_member_forbidden(
    api_client: AsyncClient,
    provisioned_org: dict,
    platform_admin_allowlist: str,
) -> None:
    _, _, member_token = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="adminmember",
    )
    response = await api_client.get(
        "/admin/overview",
        headers=auth_headers(member_token),
    )
    assert response.status_code == 403
    assert response.status_code != 404


@pytest.mark.asyncio
async def test_users_me_returns_db_role(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "platform_admin_emails", "founder-only@example.com")
    owner = await api_client.get(
        "/users/me",
        headers=auth_headers(provisioned_org["token"]),
    )
    assert owner.status_code == 200, owner.text
    body = owner.json()
    assert body["role"] == "owner"
    assert body["is_platform_admin"] is False

    _, _, member_token = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="userme",
    )
    member = await api_client.get(
        "/users/me",
        headers=auth_headers(member_token),
    )
    assert member.status_code == 200, member.text
    assert member.json()["role"] == "member"
    assert member.json()["is_platform_admin"] is False


@pytest.mark.asyncio
async def test_users_me_platform_admin_flag(
    api_client: AsyncClient,
    provisioned_org: dict,
    platform_admin_allowlist: str,
) -> None:
    response = await api_client.get(
        "/users/me",
        headers=auth_headers(provisioned_org["token"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["role"] == "owner"
    assert body["is_platform_admin"] is True


@pytest.mark.asyncio
async def test_admin_overview_requires_auth(api_client: AsyncClient) -> None:
    response = await api_client.get("/admin/overview")
    assert response.status_code == 401
