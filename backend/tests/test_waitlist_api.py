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
async def test_waitlist_signup_succeeds_without_auth(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, str]] = []

    def _fake_send(*, to_email: str, name: str) -> bool:
        sent.append({"to_email": to_email, "name": name})
        return True

    monkeypatch.setattr(
        "app.routers.waitlist.send_waitlist_confirmation",
        _fake_send,
    )

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
    assert sent == [{"to_email": email, "name": "Alex Practice"}]


@pytest.mark.asyncio
async def test_waitlist_signup_succeeds_when_send_waitlist_confirmation_raises(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If email sending blows up, signup must still return 201 (router fail-soft)."""

    def _raise_on_send(*, to_email: str, name: str) -> bool:
        raise RuntimeError(f"simulated email failure for {to_email}")

    monkeypatch.setattr(
        "app.routers.waitlist.send_waitlist_confirmation",
        _raise_on_send,
    )

    email = f"waitlist-email-fail-{uuid.uuid4().hex[:10]}@example.com"
    response = await api_client.post(
        "/waitlist",
        json={
            "name": "Jordan Pilot",
            "email": email,
            "firm": "Ridge Accounting",
            "role": "Manager",
        },
        headers={"X-Forwarded-For": "203.0.113.41"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "registered"
    assert body["id"]


@pytest.mark.asyncio
async def test_waitlist_signup_succeeds_when_resend_api_raises(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resend SDK failures are swallowed inside send_waitlist_confirmation."""
    from app.services import email as email_service

    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")

    def _boom(params: dict) -> dict:
        raise RuntimeError("simulated Resend API failure")

    monkeypatch.setattr(email_service.resend.Emails, "send", _boom)

    email = f"waitlist-resend-fail-{uuid.uuid4().hex[:10]}@example.com"
    response = await api_client.post(
        "/waitlist",
        json={
            "name": "Jordan Pilot",
            "email": email,
            "firm": "Ridge Accounting",
            "role": "Manager",
        },
        headers={"X-Forwarded-For": "203.0.113.42"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "registered"
    assert body["id"]


def test_send_waitlist_confirmation_swallows_resend_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct unit check: service logs and returns False instead of raising."""
    from app.services import email as email_service

    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")

    def _boom(params: dict) -> dict:
        raise RuntimeError("Resend API unavailable")

    monkeypatch.setattr(email_service.resend.Emails, "send", _boom)

    ok = email_service.send_waitlist_confirmation(
        to_email="pilot@example.com",
        name="Pilot",
    )
    assert ok is False


def test_send_waitlist_confirmation_skips_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import email as email_service

    monkeypatch.setattr(settings, "resend_api_key", None)
    called = {"n": 0}

    def _should_not_run(params: dict) -> dict:
        called["n"] += 1
        return {"id": "should-not"}

    monkeypatch.setattr(email_service.resend.Emails, "send", _should_not_run)
    assert email_service.send_waitlist_confirmation(to_email="a@b.com", name="A") is False
    assert called["n"] == 0


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
