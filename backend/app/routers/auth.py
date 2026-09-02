"""Clerk webhook — user/org sync including first-signup RLS bootstrap.

Tracked gap: Clerk payloads are not persisted (only structured logs). See
docs/tracked-gaps.md — "Clerk webhook payload persistence".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.config import settings
from app.db import SyncSessionLocal, set_rls_org_id
from app.models.organisation import Organisation
from app.models.user import User
from app.services.clerk_users import (
    fetch_clerk_user_primary_email,
    primary_email_from_webhook_user_payload,
)
from app.services.email import notify_founder_new_user_signup
from app.services.org_provisioning import (
    organisation_id_for_clerk_org,
    provision_first_signup,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class ClerkWebhookResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    organisation_id: str | None = None
    user_id: str | None = None
    detail: str | None = None


def _verify_webhook_signature(
    *,
    body: bytes,
    svix_id: str | None,
    svix_timestamp: str | None,
    svix_signature: str | None,
) -> None:
    """Verify Clerk/Svix webhook signature when CLERK_WEBHOOK_SECRET is configured.

    In development/test with no secret configured, verification is skipped so
    local integration tests can POST directly. Production must set the secret.
    """
    secret = settings.clerk_webhook_secret
    if not secret:
        if settings.app_env == "production":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="CLERK_WEBHOOK_SECRET is not configured",
            )
        return
    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing webhook signature headers",
        )
    signed_content = f"{svix_id}.{svix_timestamp}.{body.decode('utf-8')}".encode()
    secret_bytes = secret.encode("utf-8")
    if secret.startswith("whsec_"):
        secret_bytes = base64.b64decode(secret[len("whsec_") :])
    digest = hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    candidates = [
        part.split(",", 1)[-1].strip()
        for part in svix_signature.split(" ")
        if part.strip()
    ]
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )


def _owner_email(data: dict[str, Any], *, clerk_user_id: str | None = None) -> str:
    """Resolve owner email from webhook payload, then Clerk Users API if needed."""
    email = data.get("email") or data.get("email_address")
    if isinstance(email, str) and email:
        return email
    addresses = data.get("email_addresses") or []
    if addresses and isinstance(addresses[0], dict):
        value = addresses[0].get("email_address")
        if value:
            return str(value)
    webhook_email = primary_email_from_webhook_user_payload(data)
    if webhook_email:
        return webhook_email
    lookup_id = clerk_user_id or data.get("created_by") or data.get("user_id")
    if lookup_id:
        api_email = fetch_clerk_user_primary_email(str(lookup_id))
        if api_email:
            return api_email
    created_by = data.get("created_by") or lookup_id or "unknown"
    return f"{created_by}@users.clerk.pending"


@router.post("/webhook", response_model=ClerkWebhookResponse)
async def clerk_webhook(
    request: Request,
    svix_id: str | None = Header(default=None, alias="svix-id"),
    svix_timestamp: str | None = Header(default=None, alias="svix-timestamp"),
    svix_signature: str | None = Header(default=None, alias="svix-signature"),
) -> ClerkWebhookResponse:
    """Clerk user/org sync. Creates first org + first user under RLS (no BYPASSRLS)."""
    body = await request.body()
    _verify_webhook_signature(
        body=body,
        svix_id=svix_id,
        svix_timestamp=svix_timestamp,
        svix_signature=svix_signature,
    )
    payload = await request.json()
    event_type = str(payload.get("type") or "")
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook data")

    log = logger.bind(request_id=svix_id, event_type=event_type)

    if event_type in ("organization.created", "organisation.created"):
        response = _handle_organization_created(data, log=log)
        _log_webhook_processed(log, response)
        return response
    if event_type in (
        "organizationMembership.created",
        "organizationMembership.updated",
    ):
        response = _handle_membership(data, log=log)
        _log_webhook_processed(log, response)
        return response
    if event_type == "user.updated":
        response = _handle_user_updated(data, log=log)
        _log_webhook_processed(log, response)
        return response

    response = ClerkWebhookResponse(
        status="ignored", detail=f"Unhandled event type: {event_type}"
    )
    log.warning(
        "clerk_webhook_unhandled",
        status=response.status,
        detail=response.detail,
    )
    return response


def _log_webhook_processed(
    log: structlog.stdlib.BoundLogger,
    response: ClerkWebhookResponse,
) -> None:
    log.info(
        "clerk_webhook_processed",
        status=response.status,
        org_id=response.organisation_id,
        user_id=response.user_id,
        detail=response.detail,
    )


def _handle_organization_created(
    data: dict[str, Any],
    *,
    log: structlog.stdlib.BoundLogger,
) -> ClerkWebhookResponse:
    """First organisation for a brand-new signup — RLS bootstrap in one transaction."""
    clerk_org_id = str(data["id"])
    org_name = str(data.get("name") or "New Organisation")
    created_by = data.get("created_by")
    if not created_by:
        raise HTTPException(
            status_code=400,
            detail="organization.created requires data.created_by for first-user provisioning",
        )
    email = _owner_email(data, clerk_user_id=str(created_by))
    clerk_user_id = str(created_by)
    log = log.bind(clerk_org_id=clerk_org_id, clerk_user_id=clerk_user_id)

    with SyncSessionLocal() as session:
        try:
            provisioned = provision_first_signup(
                session,
                clerk_org_id=clerk_org_id,
                org_name=org_name,
                clerk_user_id=clerk_user_id,
                email=email,
                role="owner",
            )
            session.commit()
        except Exception:
            session.rollback()
            log.exception(
                "clerk_webhook_organization_created_failed",
                clerk_org_id=clerk_org_id,
            )
            raise

        outcome = "created" if provisioned.created else "exists"
        log.info(
            "clerk_webhook_organization_created",
            org_id=str(provisioned.organisation.id),
            user_id=str(provisioned.user.id),
            outcome=outcome,
        )
        if provisioned.created:
            try:
                notify_founder_new_user_signup(
                    org_name=org_name,
                    owner_email=email,
                    signed_up_at=provisioned.organisation.created_at,
                )
            except Exception:
                log.exception(
                    "founder_notification_unexpected_error",
                    notification_type="user_signup",
                    clerk_org_id=clerk_org_id,
                )
        return ClerkWebhookResponse(
            status=outcome,
            organisation_id=str(provisioned.organisation.id),
            user_id=str(provisioned.user.id),
        )


def _handle_membership(
    data: dict[str, Any],
    *,
    log: structlog.stdlib.BoundLogger,
) -> ClerkWebhookResponse:
    """Additional member sync — derive org UUID from Clerk org id, SET LOCAL, insert."""
    org_payload = data.get("organization") or {}
    public_user = data.get("public_user_data") or {}
    clerk_org_id = str(org_payload.get("id") or data.get("organization_id") or "")
    clerk_user_id = str(public_user.get("user_id") or data.get("user_id") or "")
    if not clerk_org_id or not clerk_user_id:
        raise HTTPException(status_code=400, detail="membership payload missing org/user ids")

    email = _owner_email({**public_user, **data}, clerk_user_id=clerk_user_id)
    role_raw = str(data.get("role") or "org:member")
    role = "member"
    if "owner" in role_raw:
        role = "owner"
    elif "admin" in role_raw:
        role = "admin"
    elif "viewer" in role_raw:
        role = "viewer"

    org_id = organisation_id_for_clerk_org(clerk_org_id)
    log = log.bind(clerk_org_id=clerk_org_id, clerk_user_id=clerk_user_id, org_id=str(org_id))

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        org = session.get(Organisation, org_id)
        if org is None:
            response = ClerkWebhookResponse(
                status="skipped",
                detail="Organisation not provisioned yet; wait for organization.created",
            )
            log.info(
                "clerk_webhook_membership_skipped",
                status=response.status,
                detail=response.detail,
            )
            return response

        existing_user = session.scalar(
            select(User).where(
                User.clerk_user_id == clerk_user_id,
                User.org_id == org_id,
            )
        )
        if existing_user is not None:
            response = ClerkWebhookResponse(
                status="exists",
                organisation_id=str(org_id),
                user_id=str(existing_user.id),
            )
            log.info(
                "clerk_webhook_membership_exists",
                status=response.status,
                user_id=str(existing_user.id),
            )
            return response

        user = User(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"findraft:user:{clerk_user_id}"),
            clerk_user_id=clerk_user_id,
            org_id=org_id,
            email=email,
            role=role,
        )
        session.add(user)
        session.commit()
        log.info(
            "clerk_webhook_membership_created",
            status="created",
            user_id=str(user.id),
            role=role,
        )
        return ClerkWebhookResponse(
            status="created",
            organisation_id=str(org_id),
            user_id=str(user.id),
        )


def _handle_user_updated(
    data: dict[str, Any],
    *,
    log: structlog.stdlib.BoundLogger,
) -> ClerkWebhookResponse:
    """Backfill or refresh user.email when Clerk sends user.updated."""
    clerk_user_id = str(data.get("id") or "")
    if not clerk_user_id:
        raise HTTPException(status_code=400, detail="user.updated requires data.id")

    email = primary_email_from_webhook_user_payload(data)
    if not email:
        email = fetch_clerk_user_primary_email(clerk_user_id)
    if not email or email.endswith("@users.clerk.pending"):
        response = ClerkWebhookResponse(
            status="skipped",
            detail="user.updated has no resolvable email",
        )
        log.info("clerk_webhook_user_updated_skipped", clerk_user_id=clerk_user_id)
        return response

    with SyncSessionLocal() as session:
        user = session.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
        if user is None:
            response = ClerkWebhookResponse(
                status="skipped",
                detail="User not provisioned yet",
            )
            log.info(
                "clerk_webhook_user_updated_skipped",
                clerk_user_id=clerk_user_id,
                detail=response.detail,
            )
            return response

        if user.email == email:
            response = ClerkWebhookResponse(
                status="exists",
                organisation_id=str(user.org_id),
                user_id=str(user.id),
            )
            log.info(
                "clerk_webhook_user_updated_unchanged",
                clerk_user_id=clerk_user_id,
                user_id=str(user.id),
            )
            return response

        set_rls_org_id(session, user.org_id)
        user.email = email
        session.commit()
        log.info(
            "clerk_webhook_user_updated",
            clerk_user_id=clerk_user_id,
            user_id=str(user.id),
            org_id=str(user.org_id),
        )
        return ClerkWebhookResponse(
            status="updated",
            organisation_id=str(user.org_id),
            user_id=str(user.id),
        )
