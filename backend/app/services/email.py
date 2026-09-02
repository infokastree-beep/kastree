"""Transactional email via Resend (waitlist + founder notifications)."""

from __future__ import annotations

import html
from datetime import datetime

import resend
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

WAITLIST_SUBJECT = "You're on the Kastree waitlist"


def _format_timestamp(when: datetime) -> str:
    if when.tzinfo is None:
        return when.isoformat() + "Z"
    return when.isoformat()


def _from_address() -> str:
    return (settings.resend_from_email or "").strip() or "Kastree <onboarding@resend.dev>"


def _send_email(
    *,
    to: list[str],
    subject: str,
    text_body: str,
    html_body: str,
    log_event_sent: str,
    log_event_failed: str,
    **log_context: object,
) -> bool:
    """Send via Resend. Never raises — callers must not block their primary flow."""
    api_key = (settings.resend_api_key or "").strip()
    if not api_key:
        logger.info(
            "email_skipped",
            reason="resend_api_key_unset",
            subject=subject,
            to=to,
            **log_context,
        )
        return False

    try:
        resend.api_key = api_key
        result = resend.Emails.send(
            {
                "from": _from_address(),
                "to": to,
                "subject": subject,
                "text": text_body,
                "html": html_body,
            }
        )
        email_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        logger.info(log_event_sent, resend_id=email_id, to=to, subject=subject, **log_context)
        return True
    except Exception:
        logger.exception(log_event_failed, to=to, subject=subject, **log_context)
        return False


def _founder_recipient() -> str | None:
    email = (settings.founder_notification_email or "").strip()
    return email or None


def _send_founder_notification(
    *,
    subject: str,
    text_body: str,
    html_body: str,
    notification_type: str,
) -> bool:
    recipient = _founder_recipient()
    if not recipient:
        logger.info(
            "founder_notification_skipped",
            reason="founder_notification_email_unset",
            notification_type=notification_type,
        )
        return False
    return _send_email(
        to=[recipient],
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        log_event_sent="founder_notification_sent",
        log_event_failed="founder_notification_failed",
        notification_type=notification_type,
    )


def send_waitlist_confirmation(*, to_email: str, name: str) -> bool:
    """Send a short waitlist confirmation. Never raises — signup must still succeed."""
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
    return _send_email(
        to=[to_email],
        subject=WAITLIST_SUBJECT,
        text_body=text_body,
        html_body=html_body,
        log_event_sent="waitlist_email_sent",
        log_event_failed="waitlist_email_failed",
        to_email=to_email,
    )


def notify_founder_waitlist_signup(
    *,
    name: str,
    email: str,
    firm: str,
    role: str,
    signed_up_at: datetime,
) -> bool:
    """Alert founder of a new public waitlist signup. Never raises."""
    subject = f"New waitlist signup: {name}"
    when = _format_timestamp(signed_up_at)
    text_body = (
        "New waitlist signup\n\n"
        f"Name: {name}\n"
        f"Email: {email}\n"
        f"Firm: {firm}\n"
        f"Role: {role}\n"
        f"Signed up: {when}\n"
    )
    html_body = (
        "<p><strong>New waitlist signup</strong></p>"
        f"<p>Name: {html.escape(name)}<br>"
        f"Email: {html.escape(email)}<br>"
        f"Firm: {html.escape(firm)}<br>"
        f"Role: {html.escape(role)}<br>"
        f"Signed up: {html.escape(when)}</p>"
    )
    return _send_founder_notification(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        notification_type="waitlist_signup",
    )


def notify_founder_new_user_signup(
    *,
    org_name: str,
    owner_email: str,
    signed_up_at: datetime,
) -> bool:
    """Alert founder of a new organisation provisioned via Clerk. Never raises."""
    subject = f"New user signup: {org_name}"
    when = _format_timestamp(signed_up_at)
    text_body = (
        "New user signup\n\n"
        f"Organisation: {org_name}\n"
        f"Owner email: {owner_email}\n"
        f"Signed up: {when}\n"
    )
    html_body = (
        "<p><strong>New user signup</strong></p>"
        f"<p>Organisation: {html.escape(org_name)}<br>"
        f"Owner email: {html.escape(owner_email)}<br>"
        f"Signed up: {html.escape(when)}</p>"
    )
    return _send_founder_notification(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        notification_type="user_signup",
    )
