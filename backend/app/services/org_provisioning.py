"""First-organisation / first-user provisioning under RLS.

Brand-new signup is an RLS chicken-and-egg: organisations_self_isolation and
users_org_isolation require app.current_org_id to already equal the new org's
id, but the row does not exist yet. We do NOT use BYPASSRLS.

Agreed approach: generate the organisation UUID in Python, SET LOCAL
app.current_org_id to that UUID in the same transaction, then INSERT the
organisations row and the first users row.

Organisation ids are uuid5(NAMESPACE_URL, "findraft:org:{clerk_org_id}") so
webhook retries SET LOCAL to the same id and remain idempotent under FORCE RLS
without a BYPASSRLS lookup-by-clerk-id.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import set_rls_org_id
from app.models.organisation import Organisation
from app.models.user import User

_ORG_NAMESPACE = uuid.NAMESPACE_URL


def organisation_id_for_clerk_org(clerk_org_id: str) -> uuid.UUID:
    """Stable internal org UUID derived from the Clerk organisation id."""
    return uuid.uuid5(_ORG_NAMESPACE, f"findraft:org:{clerk_org_id}")


def user_id_for_clerk_user(clerk_user_id: str) -> uuid.UUID:
    return uuid.uuid5(_ORG_NAMESPACE, f"findraft:user:{clerk_user_id}")


@dataclass(frozen=True)
class ProvisionedSignup:
    organisation: Organisation
    user: User
    created: bool


def provision_first_signup(
    session: Session,
    *,
    clerk_org_id: str,
    org_name: str,
    clerk_user_id: str,
    email: str,
    role: str = "owner",
) -> ProvisionedSignup:
    """Create the first organisation and owner user under FORCE RLS.

    Must run inside an open transaction. SET LOCAL is transaction-scoped
    (set_config third argument true).

    Concurrent duplicate ``organization.created`` deliveries can both pass the
    ``existing_org is None`` check before either commits; the second INSERT then
    hits a primary-key / unique violation on the deterministic org id. That
    specific IntegrityError is caught at the insert point, the transaction is
    reset, and the now-existing rows are re-fetched (created=False). Other
    errors still propagate.
    """
    org_id = organisation_id_for_clerk_org(clerk_org_id)
    user_id = user_id_for_clerk_user(clerk_user_id)
    set_rls_org_id(session, org_id)

    existing_org = session.get(Organisation, org_id)
    if existing_org is not None:
        return _existing_signup(
            session,
            org_id=org_id,
            organisation=existing_org,
            clerk_user_id=clerk_user_id,
            user_id=user_id,
            email=email,
            role=role,
        )

    organisation = Organisation(
        id=org_id,
        clerk_org_id=clerk_org_id,
        name=org_name,
    )
    user = User(
        id=user_id,
        clerk_user_id=clerk_user_id,
        org_id=org_id,
        email=email,
        role=role,
    )
    session.add(organisation)
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        # Concurrent webhook won the insert. Rollback clears the failed
        # transaction (and SET LOCAL); re-apply RLS and return the winner.
        session.rollback()
        set_rls_org_id(session, org_id)
        raced_org = session.get(Organisation, org_id)
        if raced_org is None:
            raise
        return _existing_signup(
            session,
            org_id=org_id,
            organisation=raced_org,
            clerk_user_id=clerk_user_id,
            user_id=user_id,
            email=email,
            role=role,
        )

    return ProvisionedSignup(organisation=organisation, user=user, created=True)


def _existing_signup(
    session: Session,
    *,
    org_id: uuid.UUID,
    organisation: Organisation,
    clerk_user_id: str,
    user_id: uuid.UUID,
    email: str,
    role: str,
) -> ProvisionedSignup:
    existing_user = session.scalar(
        select(User).where(
            User.clerk_user_id == clerk_user_id,
            User.org_id == org_id,
        )
    )
    if existing_user is not None:
        return ProvisionedSignup(
            organisation=organisation,
            user=existing_user,
            created=False,
        )

    existing_user = User(
        id=user_id,
        clerk_user_id=clerk_user_id,
        org_id=org_id,
        email=email,
        role=role,
    )
    session.add(existing_user)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        set_rls_org_id(session, org_id)
        organisation = session.get(Organisation, org_id) or organisation
        existing_user = session.scalar(
            select(User).where(
                User.clerk_user_id == clerk_user_id,
                User.org_id == org_id,
            )
        )
        if existing_user is None:
            raise
    return ProvisionedSignup(
        organisation=organisation,
        user=existing_user,
        created=False,
    )
