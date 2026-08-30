"""Stripe webhook API tests — signature, idempotency, event→org updates, no JWT."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.config import settings
from app.db import SyncSessionLocal, set_rls_org_id
from app.models.organisation import Organisation
from app.models.subscription_event import SubscriptionEvent
from sqlalchemy import select

WEBHOOK_SECRET = "whsec_test_findraft_stripe_secret"


def _sign_payload(payload: bytes, *, secret: str = WEBHOOK_SECRET) -> str:
    """Build a Stripe-Signature header Stripe's construct_event accepts."""
    timestamp = int(time.time())
    signed = f"{timestamp}.{payload.decode('utf-8')}"
    digest = hmac.new(
        secret.encode("utf-8"),
        signed.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def _event_payload(
    *,
    event_id: str,
    event_type: str,
    obj: dict[str, Any],
) -> bytes:
    body = {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "data": {"object": obj},
    }
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


@pytest.fixture
def stripe_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "stripe_price_id_starter", "price_starter_test")
    monkeypatch.setattr(settings, "stripe_price_id_pro", "price_pro_test")
    monkeypatch.setattr(settings, "stripe_price_id_scale", "price_scale_test")
    return WEBHOOK_SECRET


def _org_row(org_id: uuid.UUID) -> Organisation:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        session.expunge(org)
        return org


def _event_count(org_id: uuid.UUID, stripe_event_id: str) -> int:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        return len(
            list(
                session.scalars(
                    select(SubscriptionEvent).where(
                        SubscriptionEvent.stripe_event_id == stripe_event_id
                    )
                ).all()
            )
        )


@pytest.mark.asyncio
async def test_valid_signature_processes_checkout_without_jwt(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
) -> None:
    """No Authorization header — Stripe signature alone authenticates (§8.1)."""
    org_id = provisioned_org["org_id"]
    event_id = f"evt_checkout_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="checkout.session.completed",
        obj={
            "id": "cs_test_1",
            "object": "checkout.session",
            "customer": "cus_test_checkout",
            "subscription": "sub_test_checkout",
            "metadata": {
                "org_id": str(org_id),
                "subscription_tier": "starter",
            },
            "client_reference_id": str(org_id),
        },
    )
    # Explicitly omit Authorization — must succeed on Stripe-Signature alone.
    response = await api_client.post(
        "/webhooks/stripe",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": _sign_payload(payload, secret=stripe_secret),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "processed"
    assert body["organisation_id"] == str(org_id)
    # Request must succeed without a JWT (Stripe signature is the only auth).
    assert "authorization" not in {
        k.lower() for k in response.request.headers.keys()
    }

    org = _org_row(org_id)
    assert org.subscription_tier == "starter"
    assert org.subscription_status == "active"
    assert org.stripe_customer_id == "cus_test_checkout"
    assert org.stripe_subscription_id == "sub_test_checkout"
    assert _event_count(org_id, event_id) == 1


@pytest.mark.asyncio
async def test_invalid_signature_returns_400_without_processing(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
) -> None:
    org_id = provisioned_org["org_id"]
    before = _org_row(org_id)
    event_id = f"evt_bad_sig_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="checkout.session.completed",
        obj={
            "customer": "cus_should_not_apply",
            "subscription": "sub_should_not_apply",
            "metadata": {"org_id": str(org_id), "subscription_tier": "scale"},
        },
    )
    response = await api_client.post(
        "/webhooks/stripe",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": _sign_payload(payload, secret="whsec_wrong_secret"),
        },
    )
    assert response.status_code == 400, response.text
    assert "signature" in response.json()["detail"].lower()

    after = _org_row(org_id)
    assert after.subscription_tier == before.subscription_tier
    assert after.stripe_customer_id == before.stripe_customer_id
    assert _event_count(org_id, event_id) == 0


@pytest.mark.asyncio
async def test_missing_signature_returns_400_without_processing(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
) -> None:
    org_id = provisioned_org["org_id"]
    event_id = f"evt_nosig_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="customer.subscription.created",
        obj={
            "id": "sub_nosig",
            "customer": "cus_nosig",
            "metadata": {"org_id": str(org_id)},
            "items": {"data": [{"price": {"id": "price_starter_test"}}]},
            "status": "active",
        },
    )
    response = await api_client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400, response.text
    assert _event_count(org_id, event_id) == 0


@pytest.mark.asyncio
async def test_duplicate_stripe_event_id_handled_gracefully(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
) -> None:
    org_id = provisioned_org["org_id"]
    event_id = f"evt_dup_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="customer.subscription.created",
        obj={
            "id": "sub_dup",
            "customer": "cus_dup",
            "status": "active",
            "metadata": {"org_id": str(org_id)},
            "items": {"data": [{"price": {"id": "price_pro_test"}}]},
        },
    )
    headers = {
        "Content-Type": "application/json",
        "Stripe-Signature": _sign_payload(payload, secret=stripe_secret),
    }
    first = await api_client.post("/webhooks/stripe", content=payload, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "processed"

    # Fresh signature for the identical body (Stripe retries).
    headers["Stripe-Signature"] = _sign_payload(payload, secret=stripe_secret)
    second = await api_client.post("/webhooks/stripe", content=payload, headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "already_processed"
    assert second.status_code != 500
    assert _event_count(org_id, event_id) == 1

    org = _org_row(org_id)
    assert org.subscription_tier == "pro"
    assert org.subscription_status == "active"


@pytest.mark.asyncio
async def test_subscription_updated_changes_tier_and_status(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
) -> None:
    org_id = provisioned_org["org_id"]
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.stripe_customer_id = "cus_updated"
        org.stripe_subscription_id = "sub_updated"
        org.subscription_tier = "starter"
        org.subscription_status = "active"
        session.commit()

    event_id = f"evt_upd_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="customer.subscription.updated",
        obj={
            "id": "sub_updated",
            "customer": "cus_updated",
            "status": "trialing",
            "items": {"data": [{"price": {"id": "price_scale_test"}}]},
        },
    )
    response = await api_client.post(
        "/webhooks/stripe",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": _sign_payload(payload, secret=stripe_secret),
        },
    )
    assert response.status_code == 200, response.text
    org = _org_row(org_id)
    assert org.subscription_tier == "scale"
    assert org.subscription_status == "trialing"


@pytest.mark.asyncio
async def test_subscription_deleted_sets_cancelled_without_deleting_org(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
) -> None:
    org_id = provisioned_org["org_id"]
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.stripe_customer_id = "cus_del"
        org.stripe_subscription_id = "sub_del"
        org.subscription_tier = "starter"
        org.subscription_status = "active"
        session.commit()

    event_id = f"evt_del_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="customer.subscription.deleted",
        obj={
            "id": "sub_del",
            "customer": "cus_del",
            "status": "canceled",
        },
    )
    response = await api_client.post(
        "/webhooks/stripe",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": _sign_payload(payload, secret=stripe_secret),
        },
    )
    assert response.status_code == 200, response.text
    org = _org_row(org_id)
    assert org.subscription_status == "cancelled"
    # Status-only — org and tier data retained (§13.2).
    assert org.subscription_tier == "starter"
    assert org.name  # org still exists


@pytest.mark.asyncio
async def test_invoice_payment_failed_sets_past_due(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
) -> None:
    org_id = provisioned_org["org_id"]
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.stripe_customer_id = "cus_fail"
        org.stripe_subscription_id = "sub_fail"
        org.subscription_status = "active"
        session.commit()

    event_id = f"evt_fail_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="invoice.payment_failed",
        obj={
            "id": "in_fail",
            "customer": "cus_fail",
            "subscription": "sub_fail",
        },
    )
    response = await api_client.post(
        "/webhooks/stripe",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": _sign_payload(payload, secret=stripe_secret),
        },
    )
    assert response.status_code == 200, response.text
    org = _org_row(org_id)
    assert org.subscription_status == "past_due"


@pytest.mark.asyncio
async def test_subscription_created_resolves_org_via_stripe_customer_id(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
) -> None:
    """No metadata.org_id — lookup via SECURITY DEFINER + organisations.stripe_customer_id."""
    org_id = provisioned_org["org_id"]
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.stripe_customer_id = "cus_lookup_only"
        session.commit()

    event_id = f"evt_lookup_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="customer.subscription.created",
        obj={
            "id": "sub_lookup_only",
            "customer": "cus_lookup_only",
            "status": "active",
            "items": {"data": [{"price": {"id": "price_starter_test"}}]},
        },
    )
    response = await api_client.post(
        "/webhooks/stripe",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": _sign_payload(payload, secret=stripe_secret),
        },
    )
    assert response.status_code == 200, response.text
    org = _org_row(org_id)
    assert org.subscription_tier == "starter"
    assert org.stripe_subscription_id == "sub_lookup_only"
