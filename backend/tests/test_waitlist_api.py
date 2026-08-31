"""Public waitlist signup API tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.config import settings
from app.services.rate_limit import reset_rate_limits_for_tests


@pytest.fixture(autouse=True)
def _clear_waitlist_rate_limits() -> None:
    reset_rate_limits_for_tests()
    yield
    reset_rate_limits_for_tests()


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
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "registered"
    assert body["id"]


@pytest.mark.asyncio
async def test_waitlist_signup_rejects_duplicate_email(api_client: AsyncClient) -> None:
    email = f"dup-{uuid.uuid4().hex[:10]}@example.com"
    payload = {
        "name": "First Signup",
        "email": email,
        "firm": "Firm A",
        "role": "CFO",
    }
    headers = {"X-Forwarded-For": "203.0.113.11"}
    first = await api_client.post("/waitlist", json=payload, headers=headers)
    assert first.status_code == 201, first.text

    second = await api_client.post(
        "/waitlist",
        json={**payload, "name": "Second Signup", "firm": "Firm B"},
        headers=headers,
    )
    assert second.status_code == 409, second.text
    assert "already on the waitlist" in second.json()["detail"].lower()


@pytest.mark.asyncio
async def test_waitlist_signup_rate_limited_per_ip(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "waitlist_rate_limit_per_ip_per_hour", 3)
    headers = {"X-Forwarded-For": "203.0.113.99"}

    for index in range(3):
        response = await api_client.post(
            "/waitlist",
            json={
                "name": f"User {index}",
                "email": f"rate-{uuid.uuid4().hex[:8]}@example.com",
                "firm": "Rate Test LLP",
                "role": "Partner",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text

    blocked = await api_client.post(
        "/waitlist",
        json={
            "name": "Blocked",
            "email": f"rate-{uuid.uuid4().hex[:8]}@example.com",
            "firm": "Rate Test LLP",
            "role": "Partner",
        },
        headers=headers,
    )
    assert blocked.status_code == 429, blocked.text
    assert "too many" in blocked.json()["detail"].lower()
