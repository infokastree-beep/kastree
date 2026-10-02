"""Product 2 Phase 1 tenant isolation.

The local login is `findraft`, a superuser, which bypasses RLS even with
FORCE. The three RLS tests call SET ROLE findraft_app and then assert that
current_user is that role and that rolsuper and rolbypassrls are both false.
session_user stays `findraft` because SET ROLE does not change the login.
The foreign-key, re-pin, and org-id trigger tests run as the superuser login;
those constraints apply to table owners and do not depend on RLS.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.client import Client
from app.models.company import Company
from app.services.org_provisioning import provision_first_signup
from findraft.models.draft_version import DraftVersion
from findraft.models.year_end import YearEnd


def _delete_org(org_id: uuid.UUID) -> None:
    with SyncSessionLocal() as session:
        session.execute(text("RESET ROLE"))
        oid = str(org_id)
        session.execute(
            text("DELETE FROM findraft_draft_versions WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_year_ends WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text(
                "DELETE FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)"
            ),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM clients WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM notifications WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM users WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM subscription_events WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"),
            {"oid": oid},
        )
        session.commit()


def _provision(suffix: str) -> dict:
    with SyncSessionLocal() as session:
        provisioned = provision_first_signup(
            session,
            clerk_org_id=f"org_fd_{suffix}",
            org_name=f"FinDraft {suffix}",
            clerk_user_id=f"user_fd_{suffix}",
            email=f"fd-{suffix}@example.com",
            role="owner",
        )
        set_rls_org_id(session, provisioned.organisation.id)
        client = Client(org_id=provisioned.organisation.id, name=f"Client {suffix}")
        session.add(client)
        session.flush()
        company = Company(
            client_id=client.id,
            name=f"Company {suffix}",
            functional_currency="EUR",
        )
        session.add(company)
        session.flush()
        session.refresh(company)
        year_end = YearEnd(
            org_id=company.org_id,
            company_id=company.id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            pack_id="frs102-1a-ie",
            pack_version="2024.09",
        )
        session.add(year_end)
        session.flush()
        draft = DraftVersion(
            org_id=company.org_id,
            company_id=company.id,
            year_end_id=year_end.id,
            version_number=1,
            pack_id=year_end.pack_id,
            pack_version=year_end.pack_version,
        )
        session.add(draft)
        session.commit()
        return {
            "org_id": provisioned.organisation.id,
            "company_id": company.id,
            "year_end_id": year_end.id,
            "draft_id": draft.id,
        }


@pytest.fixture
def two_practices() -> Iterator[tuple[dict, dict]]:
    suffix = uuid.uuid4().hex[:8]
    first = _provision(f"a{suffix}")
    second = _provision(f"b{suffix}")
    try:
        yield first, second
    finally:
        _delete_org(first["org_id"])
        _delete_org(second["org_id"])


def _role_snapshot(session):
    return session.execute(
        text(
            """
            SELECT session_user AS login_role,
                   current_user AS executing_role,
                   r.rolsuper,
                   r.rolbypassrls
            FROM pg_roles AS r
            WHERE r.rolname = current_user
            """
        )
    ).one()


def _as_app_role(session) -> None:
    session.execute(text("SET ROLE findraft_app"))
    row = _role_snapshot(session)
    assert row.login_role == "findraft"
    assert row.executing_role == "findraft_app"
    assert row.rolsuper is False
    assert row.rolbypassrls is False
    print(
        f"executing_role={row.executing_role} login_role={row.login_role} "
        f"rolsuper={row.rolsuper} rolbypassrls={row.rolbypassrls}",
        flush=True,
    )


def _as_login_superuser(session) -> None:
    row = _role_snapshot(session)
    assert row.login_role == "findraft"
    assert row.executing_role == "findraft"
    assert row.rolsuper is True
    print(
        f"executing_role={row.executing_role} login_role={row.login_role} "
        f"rolsuper={row.rolsuper} rolbypassrls={row.rolbypassrls}",
        flush=True,
    )


def test_company_org_id_is_copied_from_client(two_practices: tuple[dict, dict]) -> None:
    first, _second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        row = session.execute(
            text("SELECT org_id FROM companies WHERE id = :id"),
            {"id": str(first["company_id"])},
        ).one()
        assert row.org_id == first["org_id"]


def test_unset_tenant_context_returns_no_rows(
    two_practices: tuple[dict, dict],
) -> None:
    with SyncSessionLocal() as session:
        try:
            _as_app_role(session)
            year_ends = session.execute(
                text("SELECT count(*) FROM findraft_year_ends")
            ).scalar_one()
            drafts = session.execute(
                text("SELECT count(*) FROM findraft_draft_versions")
            ).scalar_one()
            assert year_ends == 0
            assert drafts == 0
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_app_role_sees_only_its_practice(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            year_ids = session.execute(
                text("SELECT id FROM findraft_year_ends")
            ).scalars().all()
            draft_ids = session.execute(
                text("SELECT id FROM findraft_draft_versions")
            ).scalars().all()
            assert year_ids == [first["year_end_id"]]
            assert draft_ids == [first["draft_id"]]
            assert second["year_end_id"] not in year_ids
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_with_check_rejects_cross_tenant_insert(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="row-level security"):
                session.execute(
                    text(
                        """
                        INSERT INTO findraft_year_ends (
                          id, org_id, company_id, period_end, pack_id, pack_version
                        ) VALUES (
                          :id, :org, :company, DATE '2025-12-31',
                          'frs102-1a-ie', '2024.09'
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org": str(second["org_id"]),
                        "company": str(second["company_id"]),
                    },
                )
            session.rollback()
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_composite_fk_rejects_mismatched_company(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    """
                    INSERT INTO findraft_year_ends (
                      id, org_id, company_id, period_end, pack_id, pack_version
                    ) VALUES (
                      :id, :org, :company, DATE '2025-12-31',
                      'frs102-1a-ie', '2024.09'
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": str(first["org_id"]),
                    "company": str(second["company_id"]),
                },
            )
        session.rollback()


def test_repin_is_rejected(two_practices: tuple[dict, dict]) -> None:
    first, _second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        with pytest.raises(DBAPIError, match="already pinned"):
            session.execute(
                text(
                    """
                    UPDATE findraft_year_ends
                    SET pack_version = '2025.01'
                    WHERE id = :id
                    """
                ),
                {"id": str(first["year_end_id"])},
            )
        session.rollback()


def test_draft_pack_must_match_year_end(two_practices: tuple[dict, dict]) -> None:
    first, _second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        with pytest.raises(IntegrityError):
            session.add(
                DraftVersion(
                    org_id=first["org_id"],
                    company_id=first["company_id"],
                    year_end_id=first["year_end_id"],
                    version_number=2,
                    pack_id="frs102-1a-ie",
                    pack_version="2025.01",
                )
            )
            session.commit()
        session.rollback()
