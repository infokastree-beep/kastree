"""Tests for Clerk user email resolution."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.services.org_provisioning import organisation_id_for_clerk_org
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_clerk_webhook_organization_created_fetches_email_from_clerk_api(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real Clerk organization.created payloads omit email — resolve via Users API."""
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_api_{suffix}"
    clerk_user_id = f"user_api_{suffix}"
    expected_email = f"real-{suffix}@example.com"

    mock_user = MagicMock()
    mock_user.primary_email_address_id = "email_primary"
    mock_entry = MagicMock()
    mock_entry.id = "email_primary"
    mock_entry.email_address = expected_email
    mock_user.email_addresses = [mock_entry]

    mock_client = MagicMock()
    mock_client.users.get.return_value = mock_user
    monkeypatch.setattr(
        "app.routers.auth.fetch_clerk_user_primary_email",
        lambda clerk_id: expected_email if clerk_id == clerk_user_id else None,
    )

    payload = {
        "type": "organization.created",
        "data": {
            "id": clerk_org_id,
            "name": "API Email Org",
            "created_by": clerk_user_id,
        },
    }
    response = await api_client.post("/auth/webhook", json=payload)
    assert response.status_code == 200, response.text
    org_id = organisation_id_for_clerk_org(clerk_org_id)

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.execute(
            text("SELECT email FROM users WHERE org_id = :oid"),
            {"oid": str(org_id)},
        ).one()
        assert row[0] == expected_email
        session.execute(text("DELETE FROM users WHERE org_id = :oid"), {"oid": str(org_id)})
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"), {"oid": str(org_id)}
        )
        session.commit()


@pytest.mark.asyncio
async def test_clerk_webhook_user_updated_backfills_placeholder_email(
    api_client: AsyncClient,
) -> None:
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_uu_{suffix}"
    clerk_user_id = f"user_uu_{suffix}"
    org_id = organisation_id_for_clerk_org(clerk_org_id)
    placeholder = f"{clerk_user_id}@users.clerk.pending"
    resolved = f"resolved-{suffix}@example.com"

    create_payload = {
        "type": "organization.created",
        "data": {
            "id": clerk_org_id,
            "name": "User Updated Org",
            "created_by": clerk_user_id,
            "email": placeholder,
        },
    }
    create = await api_client.post("/auth/webhook", json=create_payload)
    assert create.status_code == 200, create.text

    update_payload = {
        "type": "user.updated",
        "data": {
            "id": clerk_user_id,
            "primary_email_address_id": "em_1",
            "email_addresses": [
                {"id": "em_1", "email_address": resolved},
            ],
        },
    }
    updated = await api_client.post("/auth/webhook", json=update_payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "updated"

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.execute(
            text("SELECT email FROM users WHERE org_id = :oid"),
            {"oid": str(org_id)},
        ).one()
        assert row[0] == resolved
        session.execute(text("DELETE FROM users WHERE org_id = :oid"), {"oid": str(org_id)})
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"), {"oid": str(org_id)}
        )
        session.commit()
