"""Public waitlist signup API tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal


@pytest.mark.asyncio
async def test_waitlist_signup_succeeds_without_auth(api_client: AsyncClient) -> None:
    email = f"waitlist-{uuid.uuid4().hex[:10]}@example.com"
    response = await api_client.post(
        "/waitlist",
        json={
            "name": "Alex Practice",
            "email": email,
            "firm": "North Lane Accounting",
            "role": "Partner",
            "approx_client_count": "12",
            "pain_point": "Rebuilding the same TB template every month",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "registered"
    assert body["id"]

    with SyncSessionLocal() as session:
        row = session.execute(
            text("SELECT email, firm FROM waitlist_signups WHERE email = :email"),
            {"email": email},
        ).one()
        assert row[0] == email
        assert row[1] == "North Lane Accounting"
        session.execute(
            text("DELETE FROM waitlist_signups WHERE email = :email"),
            {"email": email},
        )
        session.commit()


@pytest.mark.asyncio
async def test_waitlist_signup_rejects_duplicate_email(api_client: AsyncClient) -> None:
    email = f"dup-{uuid.uuid4().hex[:10]}@example.com"
    payload = {
        "name": "First Signup",
        "email": email,
        "firm": "Firm A",
        "role": "CFO",
    }
    first = await api_client.post("/waitlist", json=payload)
    assert first.status_code == 201, first.text

    second = await api_client.post(
        "/waitlist",
        json={**payload, "name": "Second Signup", "firm": "Firm B"},
    )
    assert second.status_code == 409, second.text
    assert "already on the waitlist" in second.json()["detail"].lower()

    with SyncSessionLocal() as session:
        session.execute(
            text("DELETE FROM waitlist_signups WHERE email = :email"),
            {"email": email},
        )
        session.commit()
