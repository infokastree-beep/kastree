"""Founder notification email tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
async def test_waitlist_signup_succeeds_when_founder_notification_raises(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Founder alert failures must not block getting on the waitlist."""

    def _raise_founder_notification(**_kwargs: object) -> bool:
        raise RuntimeError("simulated founder notification failure")

    monkeypatch.setattr(
        "app.routers.waitlist.send_waitlist_confirmation",
        lambda **_: True,
    )
    monkeypatch.setattr(
        "app.routers.waitlist.notify_founder_waitlist_signup",
        _raise_founder_notification,
    )

    email = f"founder-fail-{uuid.uuid4().hex[:10]}@example.com"
    response = await api_client.post(
        "/waitlist",
        json={
            "name": "Founder Fail Test",
            "email": email,
            "firm": "Signal LLP",
            "role": "Partner",
        },
        headers={"X-Forwarded-For": "203.0.113.51"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "registered"
    assert body["id"]


@pytest.mark.asyncio
async def test_clerk_webhook_succeeds_when_founder_notification_raises(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Founder alert failures must not block organisation provisioning."""

    def _raise_founder_notification(**_kwargs: object) -> bool:
        raise RuntimeError("simulated founder notification failure")

    monkeypatch.setattr(
        "app.routers.auth.notify_founder_new_user_signup",
        _raise_founder_notification,
    )

    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_founder_fail_{suffix}"
    clerk_user_id = f"user_founder_fail_{suffix}"
    response = await api_client.post(
        "/auth/webhook",
        json={
            "type": "organization.created",
            "data": {
                "id": clerk_org_id,
                "name": "Founder Fail Org",
                "created_by": clerk_user_id,
                "email": f"owner-{suffix}@example.com",
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "created"
    assert body["organisation_id"]
    assert body["user_id"]


def test_notify_founder_waitlist_signup_skips_without_recipient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import email as email_service

    monkeypatch.setattr(settings, "founder_notification_email", None)
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    called = {"n": 0}

    def _should_not_run(**_kwargs: object) -> bool:
        called["n"] += 1
        return True

    monkeypatch.setattr(email_service, "_send_email", _should_not_run)
    ok = email_service.notify_founder_waitlist_signup(
        name="Alex",
        email="alex@example.com",
        firm="North Lane",
        role="Partner",
        signed_up_at=datetime.now(timezone.utc),
    )
    assert ok is False
    assert called["n"] == 0


def test_notify_founder_new_user_signup_swallows_resend_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import email as email_service

    monkeypatch.setattr(settings, "founder_notification_email", "founder@example.com")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")

    def _boom(params: dict) -> dict:
        raise RuntimeError("Resend API unavailable")

    monkeypatch.setattr(email_service.resend.Emails, "send", _boom)
    ok = email_service.notify_founder_new_user_signup(
        org_name="Acme Practice",
        owner_email="owner@example.com",
        signed_up_at=datetime.now(timezone.utc),
    )
    assert ok is False
