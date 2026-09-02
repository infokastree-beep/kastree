"""Transactional email via Resend (waitlist confirmations first)."""

from __future__ import annotations

import html

import resend
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

WAITLIST_SUBJECT = "You're on the Kastree waitlist"


def send_waitlist_confirmation(*, to_email: str, name: str) -> bool:
    """Send a short waitlist confirmation. Never raises — signup must still succeed.

    Returns True if Resend accepted the send, False if skipped or failed.
    """
    api_key = (settings.resend_api_key or "").strip()
    if not api_key:
        logger.info(
            "waitlist_email_skipped",
            reason="resend_api_key_unset",
            to_email=to_email,
        )
        return False

    from_address = (settings.resend_from_email or "").strip() or "Kastree <onboarding@resend.dev>"
    display_name = (name or "").strip() or "there"
    safe_name = html.escape(display_name)
    text_body = (
        f"Hi {display_name},\n\n"
        "You're on the Kastree waitlist.\n\n"
        "We're opening early access to a small number of practices for structured "
        "feedback — not a public launch. We'll email you when there's a slot.\n\n"
        "No mailing-list spam from us.\n\n"
        "— Kastree\n"
    )
    html_body = (
        f"<p>Hi {safe_name},</p>"
        "<p>You're on the Kastree waitlist.</p>"
        "<p>We're opening early access to a small number of practices for structured "
        "feedback — not a public launch. We'll email you when there's a slot.</p>"
        "<p>No mailing-list spam from us.</p>"
        "<p>— Kastree</p>"
    )

    try:
        resend.api_key = api_key
        result = resend.Emails.send(
            {
                "from": from_address,
                "to": [to_email],
                "subject": WAITLIST_SUBJECT,
                "text": text_body,
                "html": html_body,
            }
        )
        email_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        logger.info(
            "waitlist_email_sent",
            to_email=to_email,
            resend_id=email_id,
        )
        return True
    except Exception:
        logger.exception(
            "waitlist_email_failed",
            to_email=to_email,
        )
        return False
