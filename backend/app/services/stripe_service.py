"""Stripe billing helpers — price→tier mapping and org billing-field updates (§4.5).

The organisations columns subscription_tier / subscription_status /
stripe_customer_id / stripe_subscription_id are written HERE (and only here)
from the Stripe webhook handler — see the comment on Organisation model.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import set_rls_org_id
from app.models.organisation import Organisation
from app.models.subscription_event import SubscriptionEvent

logger = logging.getLogger(__name__)

TierName = str  # 'free' | 'starter' | 'pro' | 'scale'


def price_id_to_tier(price_id: str | None) -> TierName | None:
    """Map a Stripe Price id to subscription_tier via configured env price ids."""
    if not price_id:
        return None
    mapping = {
        settings.stripe_price_id_starter: "starter",
        settings.stripe_price_id_pro: "pro",
        settings.stripe_price_id_scale: "scale",
    }
    return mapping.get(price_id)


def extract_price_id(stripe_object: dict[str, Any]) -> str | None:
    """Best-effort price id from Checkout Session or Subscription payloads."""
    # Checkout Session may carry metadata.price_id / metadata.subscription_tier
    metadata = stripe_object.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("price_id"):
        return str(metadata["price_id"])

    # Subscription.items.data[0].price.id
    items = stripe_object.get("items") or {}
    data = items.get("data") if isinstance(items, dict) else None
    if isinstance(data, list) and data:
        price = data[0].get("price") if isinstance(data[0], dict) else None
        if isinstance(price, dict) and price.get("id"):
            return str(price["id"])
        if isinstance(price, str):
            return price

    # Checkout line_items (if expanded) — rare in webhook payloads
    lines = stripe_object.get("line_items") or {}
    line_data = lines.get("data") if isinstance(lines, dict) else None
    if isinstance(line_data, list) and line_data:
        price = line_data[0].get("price") if isinstance(line_data[0], dict) else None
        if isinstance(price, dict) and price.get("id"):
            return str(price["id"])

    return None


def extract_customer_id(stripe_object: dict[str, Any]) -> str | None:
    customer = stripe_object.get("customer")
    if isinstance(customer, str) and customer:
        return customer
    if isinstance(customer, dict) and customer.get("id"):
        return str(customer["id"])
    return None


def extract_subscription_id(
    stripe_object: dict[str, Any], *, event_type: str
) -> str | None:
    if event_type.startswith("customer.subscription."):
        sub_id = stripe_object.get("id")
        if isinstance(sub_id, str) and sub_id.startswith("sub_"):
            return sub_id
    subscription = stripe_object.get("subscription")
    if isinstance(subscription, str) and subscription:
        return subscription
    if isinstance(subscription, dict) and subscription.get("id"):
        return str(subscription["id"])
    return None


def _lookup_org_by_stripe_subscription(
    session: Session, subscription_id: str
) -> uuid.UUID | None:
    org_id = session.execute(
        text("SELECT app_find_org_id_for_stripe_subscription(:sid)"),
        {"sid": subscription_id},
    ).scalar()
    return uuid.UUID(str(org_id)) if org_id is not None else None


def _lookup_org_by_stripe_customer(session: Session, customer_id: str) -> uuid.UUID | None:
    org_id = session.execute(
        text("SELECT app_find_org_id_for_stripe_customer(:cid)"),
        {"cid": customer_id},
    ).scalar()
    return uuid.UUID(str(org_id)) if org_id is not None else None


def resolve_org_id(
    session: Session,
    stripe_object: dict[str, Any],
    *,
    event_type: str,
) -> uuid.UUID | None:
    """Resolve organisation for a Stripe event.

    Order: metadata.org_id / client_reference_id, then SECURITY DEFINER
    id-only lookups (owned by findraft_rls_bypass) by stripe_customer_id /
    stripe_subscription_id. Does not broaden organisations_self_isolation.
    """
    metadata = stripe_object.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("org_id"):
        try:
            return uuid.UUID(str(metadata["org_id"]))
        except ValueError:
            logger.warning("Invalid metadata.org_id on Stripe object")

    client_ref = stripe_object.get("client_reference_id")
    if isinstance(client_ref, str) and client_ref:
        try:
            return uuid.UUID(client_ref)
        except ValueError:
            pass

    customer_id = extract_customer_id(stripe_object)
    subscription_id = extract_subscription_id(stripe_object, event_type=event_type)

    # When both ids are present, resolve via each SECURITY DEFINER helper and
    # reconcile. SQL uses LIMIT 1 per column — stale rows can disagree.
    if subscription_id and customer_id:
        sub_org = _lookup_org_by_stripe_subscription(session, subscription_id)
        cust_org = _lookup_org_by_stripe_customer(session, customer_id)
        if sub_org is not None and cust_org is not None:
            if sub_org == cust_org:
                return sub_org
            logger.warning(
                "Stripe org lookup mismatch for %s: customer→%s subscription→%s",
                event_type,
                cust_org,
                sub_org,
            )
            if event_type.startswith(("customer.subscription.", "invoice.")):
                return sub_org
            return cust_org
        if sub_org is not None:
            return sub_org
        if cust_org is not None:
            return cust_org
        return None

    if subscription_id:
        return _lookup_org_by_stripe_subscription(session, subscription_id)

    if customer_id:
        return _lookup_org_by_stripe_customer(session, customer_id)

    return None


def insert_subscription_event(
    session: Session,
    *,
    org_id: uuid.UUID,
    stripe_event_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> tuple[SubscriptionEvent | None, bool]:
    """Insert subscription_events row. Returns (row, already_processed).

    Duplicate stripe_event_id (UNIQUE) → IntegrityError recovery matching
    org_provisioning.py: rollback, re-SET RLS, treat as already processed when
    processed_at is set; otherwise return the existing unprocessed row.
    """
    set_rls_org_id(session, org_id)
    row = SubscriptionEvent(
        org_id=org_id,
        stripe_event_id=stripe_event_id,
        event_type=event_type,
        payload=payload,
        processed_at=None,
    )
    session.add(row)
    try:
        session.flush()
        return row, False
    except IntegrityError:
        # Concurrent / retried Stripe delivery won the unique stripe_event_id.
        session.rollback()
        set_rls_org_id(session, org_id)
        existing = session.scalar(
            select(SubscriptionEvent).where(
                SubscriptionEvent.stripe_event_id == stripe_event_id
            )
        )
        if existing is None:
            raise
        return existing, existing.processed_at is not None


def apply_organisation_billing_update(
    session: Session,
    *,
    org_id: uuid.UUID,
    event_type: str,
    stripe_object: dict[str, Any],
) -> Organisation:
    """Write organisations billing fields — the ONE allowed direct writer (§4.5).

    Mirrors Organisation model comment: billing fields must only ever be written
    by the Stripe webhook handler, not general org-update code.
    """
    set_rls_org_id(session, org_id)
    organisation = session.get(Organisation, org_id)
    if organisation is None:
        raise ValueError(f"Organisation {org_id} not found for Stripe event")

    customer_id = extract_customer_id(stripe_object)
    subscription_id = extract_subscription_id(stripe_object, event_type=event_type)
    price_id = extract_price_id(stripe_object)
    tier = price_id_to_tier(price_id)
    # Allow explicit metadata.subscription_tier when price id not configured (tests/dev).
    metadata = stripe_object.get("metadata") or {}
    if tier is None and isinstance(metadata, dict) and metadata.get("subscription_tier"):
        candidate = str(metadata["subscription_tier"])
        if candidate in {"free", "starter", "pro", "scale"}:
            tier = candidate

    if event_type in (
        "checkout.session.completed",
        "customer.subscription.created",
    ):
        if customer_id:
            organisation.stripe_customer_id = customer_id
        if subscription_id:
            organisation.stripe_subscription_id = subscription_id
        if tier:
            organisation.subscription_tier = tier
        organisation.subscription_status = "active"

    elif event_type == "customer.subscription.updated":
        if customer_id:
            organisation.stripe_customer_id = customer_id
        if subscription_id:
            organisation.stripe_subscription_id = subscription_id
        if tier:
            organisation.subscription_tier = tier
        stripe_status = str(stripe_object.get("status") or "")
        organisation.subscription_status = _map_stripe_subscription_status(stripe_status)

    elif event_type == "customer.subscription.deleted":
        # §13.2 Immediate downgrades — status change only; do NOT delete org data.
        organisation.subscription_status = "cancelled"
        # Tier remains until they re-subscribe; feature gating uses status + tier.

    elif event_type == "invoice.payment_failed":
        organisation.subscription_status = "past_due"
        if customer_id and not organisation.stripe_customer_id:
            organisation.stripe_customer_id = customer_id
        if subscription_id and not organisation.stripe_subscription_id:
            organisation.stripe_subscription_id = subscription_id

    session.flush()
    return organisation


def mark_event_processed(event_row: SubscriptionEvent) -> None:
    event_row.processed_at = datetime.now(timezone.utc)


def _map_stripe_subscription_status(stripe_status: str) -> str:
    """Map Stripe subscription.status onto organisations.subscription_status CHECK."""
    mapping = {
        "active": "active",
        "trialing": "trialing",
        "past_due": "past_due",
        "canceled": "cancelled",
        "unpaid": "past_due",
        "incomplete": "past_due",
        "incomplete_expired": "cancelled",
        "paused": "past_due",
    }
    return mapping.get(stripe_status, "active")
