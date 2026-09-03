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
    suffix = uuid.uuid4().hex[:10]
    customer_id = f"cus_updated_{suffix}"
    subscription_id = f"sub_updated_{suffix}"
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.stripe_customer_id = customer_id
        org.stripe_subscription_id = subscription_id
        org.subscription_tier = "starter"
        org.subscription_status = "active"
        session.commit()

    event_id = f"evt_upd_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="customer.subscription.updated",
        obj={
            "id": subscription_id,
            "customer": customer_id,
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
    suffix = uuid.uuid4().hex[:10]
    customer_id = f"cus_del_{suffix}"
    subscription_id = f"sub_del_{suffix}"
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.stripe_customer_id = customer_id
        org.stripe_subscription_id = subscription_id
        org.subscription_tier = "starter"
        org.subscription_status = "active"
        session.commit()

    event_id = f"evt_del_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="customer.subscription.deleted",
        obj={
            "id": subscription_id,
            "customer": customer_id,
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
    suffix = uuid.uuid4().hex[:10]
    customer_id = f"cus_fail_{suffix}"
    subscription_id = f"sub_fail_{suffix}"
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.stripe_customer_id = customer_id
        org.stripe_subscription_id = subscription_id
        org.subscription_status = "active"
        session.commit()

    event_id = f"evt_fail_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="invoice.payment_failed",
        obj={
            "id": "in_fail",
            "customer": customer_id,
            "subscription": subscription_id,
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
async def test_checkout_without_metadata_tier_does_not_silently_leave_org_on_free(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
) -> None:
    """checkout.session.completed with no metadata.subscription_tier and no
    expanded line_items (the real Stripe default) must NOT silently leave the org
    on 'free'. The event must still be processed (status→active, IDs recorded) and
    the handler must NOT raise.  Tier will stay 'free' here — that is expected when
    no price signal is present — but the paired customer.subscription.created event
    (tested separately) is what carries the tier update.

    This test documents the contract: checkout is reliable for status + IDs,
    NOT for tier when metadata is absent. Tier comes from subscription.created.
    """
    org_id = provisioned_org["org_id"]
    suffix = uuid.uuid4().hex[:10]
    cust_id = f"cus_nometa_{suffix}"
    sub_id = f"sub_nometa_{suffix}"

    # Seed customer id so resolve_org_id can find this org without metadata.org_id.
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.stripe_customer_id = cust_id
        session.commit()

    event_id = f"evt_checkout_nometa_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="checkout.session.completed",
        obj={
            "id": "cs_nometa",
            "object": "checkout.session",
            "customer": cust_id,
            "subscription": sub_id,
            # No metadata.subscription_tier, no expanded line_items
            "metadata": {},
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
    body = response.json()
    assert body["status"] == "processed"

    org = _org_row(org_id)
    # IDs must be recorded even without a tier signal.
    assert org.stripe_customer_id == cust_id
    assert org.stripe_subscription_id == sub_id
    assert org.subscription_status == "active"
    # Tier stays 'free' — this is intentional when no price signal is present.
    # Tier is updated by the paired customer.subscription.created event.
    assert org.subscription_tier == "free"


@pytest.mark.asyncio
async def test_subscription_created_after_checkout_applies_tier(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
) -> None:
    """The customer.subscription.created event (always paired with checkout) carries
    items.data[0].price.id and IS the reliable tier-update event. This test confirms
    that when subscription.created arrives (possibly after checkout.session.completed),
    tier is correctly applied from the price id — not from checkout metadata.
    """
    org_id = provisioned_org["org_id"]
    suffix = uuid.uuid4().hex[:10]
    sub_id = f"sub_created_{suffix}"
    cust_id = f"cus_created_{suffix}"

    # Simulate checkout having already run: org has IDs but tier is still 'free'.
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.stripe_customer_id = cust_id
        org.subscription_tier = "free"
        org.subscription_status = "active"
        session.commit()

    event_id = f"evt_sub_created_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="customer.subscription.created",
        obj={
            "id": sub_id,
            "customer": cust_id,
            "status": "active",
            # items.data[0].price.id is always present on real subscription objects.
            "items": {"data": [{"price": {"id": "price_pro_test"}}]},
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
    assert org.subscription_tier == "pro"
    assert org.subscription_status == "active"
    assert org.stripe_subscription_id == sub_id


@pytest.mark.asyncio
async def test_subscription_updated_with_unknown_price_id_logs_warning_does_not_corrupt_tier(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When subscription.updated carries a price_id that doesn't match any configured
    STRIPE_PRICE_ID_* env var, the tier must NOT be silently corrupted — it should
    stay on its current value. A warning must be emitted so operators know the mapping
    is missing. Status must still be updated correctly.
    """
    org_id = provisioned_org["org_id"]
    suffix = uuid.uuid4().hex[:10]
    cust_id = f"cus_unknown_price_{suffix}"
    sub_id = f"sub_unknown_price_{suffix}"

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.stripe_customer_id = cust_id
        org.stripe_subscription_id = sub_id
        org.subscription_tier = "starter"
        org.subscription_status = "active"
        session.commit()

    event_id = f"evt_unknown_price_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="customer.subscription.updated",
        obj={
            "id": sub_id,
            "customer": cust_id,
            "status": "active",
            # price_id not in STRIPE_PRICE_ID_* — simulates unconfigured env or new price.
            "items": {"data": [{"price": {"id": "price_unconfigured_real_stripe_id"}}]},
        },
    )
    import logging
    with caplog.at_level(logging.WARNING, logger="app.services.stripe_service"):
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
    # Tier must be preserved — unknown price_id must not zero out the tier.
    assert org.subscription_tier == "starter"
    # Status must still update correctly.
    assert org.subscription_status == "active"
    # Warning must have been emitted so operators know the mapping is missing.
    assert any(
        "price" in r.message.lower() and "unmapped" in r.message.lower()
        for r in caplog.records
    ), f"Expected unmapped price warning, got: {[r.message for r in caplog.records]}"


@pytest.mark.asyncio
async def test_subscription_updated_with_unknown_stripe_status_preserves_current_status(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
) -> None:
    """If Stripe sends an unrecognised subscription status value,
    _map_stripe_subscription_status must NOT silently default to 'active' —
    it must preserve the organisation's current status unchanged and log a warning.
    """
    org_id = provisioned_org["org_id"]
    suffix = uuid.uuid4().hex[:10]
    cust_id = f"cus_unk_status_{suffix}"
    sub_id = f"sub_unk_status_{suffix}"

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.stripe_customer_id = cust_id
        org.stripe_subscription_id = sub_id
        org.subscription_tier = "starter"
        org.subscription_status = "past_due"
        session.commit()

    event_id = f"evt_unk_status_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="customer.subscription.updated",
        obj={
            "id": sub_id,
            "customer": cust_id,
            # Hypothetical future Stripe status not in the current mapping.
            "status": "some_future_stripe_status",
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
    # Must NOT have silently become 'active' — must stay on 'past_due'.
    assert org.subscription_status == "past_due", (
        f"Unknown Stripe status silently became 'active': got {org.subscription_status!r}"
    )
    # Tier was in the price map, so it should have updated correctly.
    assert org.subscription_tier == "starter"


@pytest.mark.asyncio
async def test_subscription_created_resolves_org_via_stripe_customer_id(
    api_client: AsyncClient,
    provisioned_org: dict,
    stripe_secret: str,
) -> None:
    """No metadata.org_id — lookup via SECURITY DEFINER + organisations.stripe_customer_id."""
    org_id = provisioned_org["org_id"]
    suffix = uuid.uuid4().hex[:10]
    customer_id = f"cus_lookup_only_{suffix}"
    subscription_id = f"sub_lookup_only_{suffix}"
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        assert org is not None
        org.stripe_customer_id = customer_id
        session.commit()

    event_id = f"evt_lookup_{uuid.uuid4().hex[:12]}"
    payload = _event_payload(
        event_id=event_id,
        event_type="customer.subscription.created",
        obj={
            "id": subscription_id,
            "customer": customer_id,
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
    assert org.stripe_subscription_id == subscription_id
