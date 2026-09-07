"""Public contact form — POST /contact (no JWT)."""

from __future__ import annotations

from datetime import timedelta

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.config import settings
from app.services.email import notify_founder_contact_message
from app.services.rate_limit import enforce_rate_limit

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["contact"])


class ContactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    message: str = Field(min_length=1, max_length=5000)


class ContactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


@router.post(
    "/contact",
    status_code=status.HTTP_200_OK,
    response_model=ContactResponse,
)
async def submit_contact(
    request: Request,
    body: ContactRequest,
) -> ContactResponse:
    """Forward a public contact message to the founder inbox via Resend."""
    enforce_rate_limit(
        request,
        key_prefix="contact",
        max_requests=settings.waitlist_rate_limit_per_ip_per_hour,
        window=timedelta(hours=1),
    )

    name = body.name.strip()
    email = str(body.email).strip().lower()
    message = body.message.strip()
    if not name or not message:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Name and message are required.",
        )

    try:
        sent = notify_founder_contact_message(
            name=name,
            email=email,
            message=message,
        )
    except Exception:
        logger.exception("contact_founder_notification_unexpected_error")
        sent = False

    if not sent:
        logger.warning(
            "contact_message_not_delivered",
            reason="resend_or_founder_unset_or_failed",
            from_email=email,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "We couldn't send your message just now. "
                "Email infokastree@gmail.com directly."
            ),
        )

    return ContactResponse(status="sent")
