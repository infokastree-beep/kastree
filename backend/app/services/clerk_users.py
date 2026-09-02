"""Clerk Users API helpers — resolve primary email for provisioning."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from clerk_backend_api import Clerk

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _clerk_client() -> Clerk | None:
    secret = settings.clerk_secret_key
    if not secret:
        return None
    return Clerk(bearer_auth=secret)


def primary_email_from_clerk_user(user: Any) -> str | None:
    """Extract the primary email from a Clerk User API object."""
    if user is None:
        return None
    addresses = getattr(user, "email_addresses", None) or []
    primary_id = getattr(user, "primary_email_address_id", None)
    if primary_id and addresses:
        for entry in addresses:
            entry_id = getattr(entry, "id", None)
            if entry_id == primary_id:
                value = getattr(entry, "email_address", None)
                if isinstance(value, str) and value:
                    return value
    for entry in addresses:
        value = getattr(entry, "email_address", None)
        if isinstance(value, str) and value:
            return value
    return None


def fetch_clerk_user_primary_email(clerk_user_id: str) -> str | None:
    """Look up a Clerk user's primary email via the Backend API."""
    client = _clerk_client()
    if client is None:
        logger.warning("clerk_secret_key unset; cannot fetch user email for %s", clerk_user_id)
        return None
    try:
        user = client.users.get(user_id=clerk_user_id)
    except Exception:
        logger.exception("clerk_users_get_failed", extra={"clerk_user_id": clerk_user_id})
        return None
    return primary_email_from_clerk_user(user)


def primary_email_from_webhook_user_payload(data: dict[str, Any]) -> str | None:
    """Resolve email from a Clerk user.* webhook payload."""
    addresses = data.get("email_addresses") or []
    primary_id = data.get("primary_email_address_id")
    if primary_id and addresses:
        for entry in addresses:
            if isinstance(entry, dict) and entry.get("id") == primary_id:
                value = entry.get("email_address")
                if isinstance(value, str) and value:
                    return value
    for entry in addresses:
        if isinstance(entry, dict):
            value = entry.get("email_address")
            if isinstance(value, str) and value:
                return value
    return None
