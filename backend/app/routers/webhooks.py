"""Stripe webhooks — /webhooks/stripe (§4.5 / §9.1 subscription_events).

JWT-exempt per Cursor Rules §8.1 (alongside /auth/webhook). Stripe calls this
directly; authenticity is the Stripe-Signature check, not a user session.
"""

from __future__ import annotations

import logging
from typing import Any

import stripe
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SyncSessionLocal, set_rls_org_id
from app.services.stripe_service import (
    apply_organisation_billing_update,
    insert_subscription_event,
    mark_event_processed,
    resolve_org_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_HANDLED_EVENT_TYPES = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_failed",
    }
)


class StripeWebhookResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    event_type: str | None = None
    organisation_id: str | None = None
    detail: str | None = None


def _construct_stripe_event(payload: bytes, sig_header: str | None) -> stripe.Event:
    """Verify Stripe-Signature against STRIPE_WEBHOOK_SECRET; raise 400 on failure.

    This is the single most important gate on this endpoint: an unverified payload
    must never be processed (Cursor Rules §8 defence-in-depth).
    """
    secret = settings.stripe_webhook_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="STRIPE_WEBHOOK_SECRET is not configured",
        )
    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header",
        )
    try:
        # --- signature verification (do not process payload if this raises) ---
        return stripe.Webhook.construct_event(payload, sig_header, secret)
    except ValueError as exc:
        # Invalid payload
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe payload",
        ) from exc
    except stripe.SignatureVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe signature",
        ) from exc


@router.post("/stripe", response_model=StripeWebhookResponse)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> StripeWebhookResponse:
    """Stripe subscription event webhook — no JWT; signature is the auth."""
    payload = await request.body()
    event = _construct_stripe_event(payload, stripe_signature)

    event_id = str(event["id"])
    event_type = str(event["type"])
    event_data_object = event["data"]["object"]
    if not isinstance(event_data_object, dict):
        raise HTTPException(status_code=400, detail="Invalid event data.object")

    # Full event dict for subscription_events.payload (event-sourcing log).
    payload_dict: dict[str, Any] = dict(event)

    if event_type not in _HANDLED_EVENT_TYPES:
        return StripeWebhookResponse(
            status="ignored",
            event_type=event_type,
            detail=f"Unhandled event type: {event_type}",
        )

    with SyncSessionLocal() as session:
        try:
            return _process_stripe_event(
                session,
                stripe_event_id=event_id,
                event_type=event_type,
                stripe_object=event_data_object,
                payload_dict=payload_dict,
            )
        except HTTPException:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            logger.exception("Stripe webhook failed for %s (%s)", event_id, event_type)
            raise


def _process_stripe_event(
    session: Session,
    *,
    stripe_event_id: str,
    event_type: str,
    stripe_object: dict[str, Any],
    payload_dict: dict[str, Any],
) -> StripeWebhookResponse:
    org_id = resolve_org_id(session, stripe_object, event_type=event_type)
    if org_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot resolve organisation for Stripe event "
                "(need metadata.org_id, client_reference_id, or known stripe customer/subscription)"
            ),
        )

    event_row, already_processed = insert_subscription_event(
        session,
        org_id=org_id,
        stripe_event_id=stripe_event_id,
        event_type=event_type,
        payload=payload_dict,
    )
    if already_processed:
        session.commit()
        return StripeWebhookResponse(
            status="already_processed",
            event_type=event_type,
            organisation_id=str(org_id),
            detail="Duplicate stripe_event_id — no re-application",
        )

    assert event_row is not None

    # Organisation billing write — sole allowed path for these columns
    # (see Organisation model: "write only from the Stripe webhook handler (§4.5)").
    set_rls_org_id(session, org_id)
    apply_organisation_billing_update(
        session,
        org_id=org_id,
        event_type=event_type,
        stripe_object=stripe_object,
    )
    mark_event_processed(event_row)
    session.commit()

    return StripeWebhookResponse(
        status="processed",
        event_type=event_type,
        organisation_id=str(org_id),
    )
