"""Billing — Stripe Checkout session creation for paid tier upgrades.

subscription_tier / subscription_status / stripe_* on organisations are still
written ONLY by the Stripe webhook (stripe_service.apply_organisation_billing_update).
This router creates Checkout Sessions; it never mutates those columns.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import aset_rls_org_id
from app.dependencies import AuthContext, get_auth_context, get_db_session
from app.models.organisation import Organisation
from app.models.user import User
from app.services.tier_limits import PAID_TIERS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

PaidTier = Literal["starter", "pro", "scale"]


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: PaidTier


class CheckoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkout_url: str
    session_id: str
    tier: PaidTier


def _price_id_for_tier(tier: PaidTier) -> str:
    mapping = {
        "starter": settings.stripe_price_id_starter,
        "pro": settings.stripe_price_id_pro,
        "scale": settings.stripe_price_id_scale,
    }
    price_id = mapping[tier]
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Stripe price for tier '{tier}' is not configured. "
                "Set STRIPE_PRICE_ID_STARTER / PRO / SCALE."
            ),
        )
    return price_id


def _frontend_base_url() -> str:
    if settings.frontend_base_url:
        return settings.frontend_base_url.rstrip("/")
    origins = [
        origin.strip()
        for origin in settings.cors_origins.split(",")
        if origin.strip()
    ]
    if origins:
        return origins[0].rstrip("/")
    return "https://www.kastree.ie"


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    body: CheckoutRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CheckoutResponse:
    """Create a Stripe Checkout Session (subscription) for a paid tier upgrade.

    Does not write organisations.subscription_* — webhook remains sole writer.
    """
    if body.tier not in PAID_TIERS:
        raise HTTPException(status_code=400, detail="Invalid tier")

    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured (STRIPE_SECRET_KEY missing)",
        )

    await aset_rls_org_id(session, auth.org_id)
    org = await session.get(Organisation, auth.org_id)
    if org is None:
        raise HTTPException(status_code=401, detail="Unknown organisation")

    user = await session.get(User, auth.user_id)
    customer_email = user.email if user is not None else None

    price_id = _price_id_for_tier(body.tier)
    stripe.api_key = settings.stripe_secret_key

    frontend = _frontend_base_url()
    success_url = f"{frontend}/pricing?checkout=success&tier={body.tier}"
    cancel_url = f"{frontend}/pricing?checkout=cancelled"

    metadata = {
        "org_id": str(auth.org_id),
        "subscription_tier": body.tier,
        "price_id": price_id,
    }

    try:
        params: dict[str, object] = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": str(auth.org_id),
            "metadata": metadata,
            "subscription_data": {"metadata": metadata},
            "allow_promotion_codes": True,
        }
        # Reuse existing Stripe customer when webhook already linked one —
        # read-only; we do not SET stripe_customer_id here.
        if org.stripe_customer_id:
            params["customer"] = org.stripe_customer_id
        elif customer_email:
            params["customer_email"] = customer_email

        checkout = stripe.checkout.Session.create(**params)
    except stripe.StripeError as exc:
        logger.exception("Stripe Checkout Session.create failed for org %s", auth.org_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not start Stripe Checkout. Try again or contact support.",
        ) from exc

    url = checkout.get("url") if isinstance(checkout, dict) else getattr(checkout, "url", None)
    session_id = (
        checkout.get("id") if isinstance(checkout, dict) else getattr(checkout, "id", None)
    )
    if not url or not session_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe Checkout did not return a session URL",
        )

    return CheckoutResponse(
        checkout_url=str(url),
        session_id=str(session_id),
        tier=body.tier,
    )
