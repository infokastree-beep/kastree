"""Public waitlist — POST /waitlist (no JWT)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import SyncSessionLocal
from app.models.waitlist_signup import WaitlistSignup
from app.schemas.waitlist import WaitlistSignupRequest, WaitlistSignupResponse
from app.services.email import send_waitlist_confirmation
from app.services.rate_limit import enforce_rate_limit

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["waitlist"])


@router.post(
    "/waitlist",
    status_code=status.HTTP_201_CREATED,
    response_model=WaitlistSignupResponse,
)
async def create_waitlist_signup(
    request: Request,
    body: WaitlistSignupRequest,
) -> WaitlistSignupResponse:
    """Record a public waitlist signup. No authentication required."""
    enforce_rate_limit(
        request,
        key_prefix="waitlist",
        max_requests=settings.waitlist_rate_limit_per_ip_per_hour,
        window=timedelta(hours=1),
    )

    signup_id = uuid.uuid4()
    name = body.name.strip()
    email = body.email.strip().lower()
    signup = WaitlistSignup(
        id=signup_id,
        name=name,
        email=email,
        firm=body.firm.strip(),
        role=body.role.strip(),
        approx_client_count=(
            body.approx_client_count.strip() if body.approx_client_count else None
        ),
        pain_point=body.pain_point.strip() if body.pain_point else None,
    )
    with SyncSessionLocal() as session:
        session.add(signup)
        try:
            session.flush()
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is already on the waitlist.",
            ) from exc

    # After commit so a Resend outage never rolls back the signup.
    # send_waitlist_confirmation is itself fail-soft; catch here as belt-and-braces.
    try:
        send_waitlist_confirmation(to_email=email, name=name)
    except Exception:
        logger.exception(
            "waitlist_email_unexpected_error",
            to_email=email,
            signup_id=str(signup_id),
        )

    return WaitlistSignupResponse(id=str(signup_id))
