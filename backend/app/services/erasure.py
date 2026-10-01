"""GDPR erasure that does not delete accounting records.

Personal data on the user and the client name are replaced. Archives and the
audit log are left as they were written. See retention.RETENTION_POLICY_STATEMENT.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.user import User
from app.services.audit import append_audit_log
from app.services.ownership import get_owned_client
from app.services.retention import (
    ERASED_EMAIL_DOMAIN,
    REDACTED_CLIENT_NAME,
    RETAINED_ON_ERASURE,
    RETENTION_POLICY_STATEMENT,
)


class ErasureRejected(Exception):
    def __init__(self, detail: str, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def erased_email(user_id: uuid.UUID) -> str:
    return f"erased-{user_id}@{ERASED_EMAIL_DOMAIN}"


def erased_login(user_id: uuid.UUID) -> str:
    return f"erased-{user_id}"


def user_is_erased(user: User) -> bool:
    return user.email == erased_email(user.id) and user.clerk_user_id == erased_login(
        user.id
    )


async def erase_client(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    client_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> tuple[bool, str]:
    """Replace the client name. Returns whether this call changed the row."""
    await aset_rls_org_id(session, org_id)
    client = await get_owned_client(
        session, client_id=client_id, org_id=org_id, include_deleted=True
    )
    if client.name == REDACTED_CLIENT_NAME:
        return False, RETENTION_POLICY_STATEMENT
    client.name = REDACTED_CLIENT_NAME
    await session.flush()
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=actor_user_id,
        action="erasure",
        entity_type="client",
        entity_id=client.id,
        old_value=None,
        new_value={
            "name": REDACTED_CLIENT_NAME,
            "retained": list(RETAINED_ON_ERASURE),
        },
    )
    return True, RETENTION_POLICY_STATEMENT


async def erase_user(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role: str,
    target_user_id: uuid.UUID,
) -> tuple[bool, str]:
    """Replace the user's email and login id. The user row stays."""
    await aset_rls_org_id(session, org_id)
    target = await session.get(User, target_user_id)
    if target is None or target.org_id != org_id:
        raise ErasureRejected("User not found", 404)
    if actor_role != "owner" and target.role == "owner":
        raise ErasureRejected(
            "You don't have permission to access this resource.",
            403,
        )
    if user_is_erased(target):
        return False, RETENTION_POLICY_STATEMENT
    if target.role == "owner":
        remaining = await _live_owner_count(session, org_id=org_id)
        if remaining <= 1:
            raise ErasureRejected("The last owner cannot be erased", 409)
    target.email = erased_email(target.id)
    target.clerk_user_id = erased_login(target.id)
    await session.flush()
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=actor_user_id,
        action="erasure",
        entity_type="user",
        entity_id=target.id,
        old_value=None,
        new_value={"email": "erased", "clerk_user_id": "erased"},
    )
    return True, RETENTION_POLICY_STATEMENT


async def _live_owner_count(session: AsyncSession, *, org_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.org_id == org_id,
            User.role == "owner",
            User.email.not_like(f"%@{ERASED_EMAIL_DOMAIN}"),
        )
    )
    return int(count or 0)
