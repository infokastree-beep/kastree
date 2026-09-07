"""Client-count limits by subscription_tier."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.client import Client
from app.models.organisation import Organisation
from app.services.tier_limits import CLIENT_LIMITS, format_client_limit_message
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_free_tier_blocks_fourth_client(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    org_id = provisioned_org["org_id"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.subscription_tier = "free"
        org.subscription_status = "active"
        # Soft-delete any pre-seeded clients from the provision fixture path.
        existing = list(
            session.scalars(
                select(Client).where(
                    Client.org_id == org_id, Client.is_deleted.is_(False)
                )
            ).all()
        )
        for row in existing:
            row.is_deleted = True
        session.commit()

    created_ids: list[str] = []
    for index in range(CLIENT_LIMITS["free"]):
        response = await api_client.post(
            "/clients",
            headers=headers,
            json={"name": f"Limit Test Client {index + 1}-{uuid.uuid4().hex[:6]}"},
        )
        assert response.status_code == 201, response.text
        created_ids.append(response.json()["id"])

    blocked = await api_client.post(
        "/clients",
        headers=headers,
        json={"name": f"Over Limit {uuid.uuid4().hex[:6]}"},
    )
    assert blocked.status_code == 403, blocked.text
    detail = blocked.json()["detail"]
    assert detail["code"] == "CLIENT_LIMIT_REACHED"
    assert detail["limit"] == 3
    assert detail["upgrade_url"] == "/pricing"
    assert detail["message"] == format_client_limit_message(3)
    assert "Upgrade to add more clients" in detail["message"]


@pytest.mark.asyncio
async def test_starter_tier_allows_ten_clients(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    org_id = provisioned_org["org_id"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.subscription_tier = "starter"
        existing = list(
            session.scalars(
                select(Client).where(
                    Client.org_id == org_id, Client.is_deleted.is_(False)
                )
            ).all()
        )
        for row in existing:
            row.is_deleted = True
        session.commit()

    for index in range(CLIENT_LIMITS["starter"]):
        response = await api_client.post(
            "/clients",
            headers=headers,
            json={"name": f"Starter Cap {index + 1}-{uuid.uuid4().hex[:6]}"},
        )
        assert response.status_code == 201, response.text

    blocked = await api_client.post(
        "/clients",
        headers=headers,
        json={"name": f"Starter Over {uuid.uuid4().hex[:6]}"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["limit"] == 10
