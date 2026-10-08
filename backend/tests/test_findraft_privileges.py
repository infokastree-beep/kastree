"""Privileges of the production login named findraft.

The parity job logs in as that role (NOSUPERUSER, NOBYPASSRLS). A superuser
login bypasses row-level security even when FORCE is on, so the cross-practice
test skips there. The parity job is the gate for that test.

Product 1 trial-balance delete and client delete are soft. They set
is_deleted and deleted_at and insert archived_records. They do not delete
the row, so they do not fire ON DELETE CASCADE or ON DELETE SET NULL, and
they do not update or delete an append-only table. Failed-parse re-upload
and statement regenerate still delete processing_jobs and
financial_statements, which keep DELETE.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import SyncSessionLocal, set_rls_org_id
from app.services.org_provisioning import provision_first_signup

_BACKEND = Path(__file__).resolve().parents[1]

# No append-only trigger. Still INSERT-only, matching the privilege SQL.
_APPEND_ONLY_WITHOUT_TRIGGER = (
    "archived_records",
    "findraft_draft_operations",
)

# Status guards. The import worker updates these while status is pending.
# The privilege SQL must not treat their trigger names as fully immutable.
_VERSION_TABLES = ("findraft_tb_versions", "findraft_fa_versions")


def _login_bypasses_rls(session) -> bool:
    row = session.execute(
        text(
            """
            SELECT rolsuper, rolbypassrls
            FROM pg_roles
            WHERE rolname = current_user
            """
        )
    ).one()
    return bool(row.rolsuper or row.rolbypassrls)


def _drop_practice(org_id: uuid.UUID) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text("DELETE FROM clients WHERE org_id = :org"),
            {"org": str(org_id)},
        )
        session.execute(
            text("DELETE FROM users WHERE org_id = :org"),
            {"org": str(org_id)},
        )
        session.execute(
            text("DELETE FROM organisations WHERE id = :org"),
            {"org": str(org_id)},
        )
        session.commit()


def test_findraft_cannot_read_or_write_another_practice() -> None:
    """One read and one write, both as the current login, against a second practice."""
    suffix = uuid.uuid4().hex[:10]
    created: list[uuid.UUID] = []
    try:
        with SyncSessionLocal() as session:
            if _login_bypasses_rls(session):
                pytest.skip(
                    "This login bypasses row-level security. "
                    "The parity job runs this test as findraft."
                )
            for label in ("a", "b"):
                provisioned = provision_first_signup(
                    session,
                    clerk_org_id=f"org_priv_{label}_{suffix}",
                    org_name=f"Privilege {label} {suffix}",
                    clerk_user_id=f"user_priv_{label}_{suffix}",
                    email=f"priv-{label}-{suffix}@example.com",
                    role="owner",
                )
                created.append(provisioned.organisation.id)
            org_a, org_b = created
            set_rls_org_id(session, org_b)
            client_b = uuid.uuid4()
            session.execute(
                text(
                    """
                    INSERT INTO clients (id, org_id, name)
                    VALUES (:id, :org, :name)
                    """
                ),
                {
                    "id": str(client_b),
                    "org": str(org_b),
                    "name": f"Client {suffix}",
                },
            )
            session.commit()

        with SyncSessionLocal() as session:
            set_rls_org_id(session, org_a)
            visible = session.execute(
                text("SELECT id FROM clients WHERE id = :id"),
                {"id": str(client_b)},
            ).scalar_one_or_none()
            assert visible is None
            with pytest.raises(DBAPIError, match="row-level security policy"):
                session.execute(
                    text(
                        """
                        INSERT INTO clients (id, org_id, name)
                        VALUES (:id, :org, 'cross practice')
                        """
                    ),
                    {"id": str(uuid.uuid4()), "org": str(org_b)},
                )
                session.commit()
            session.rollback()
    finally:
        for org_id in created:
            _drop_practice(org_id)


def _grants(session) -> list[tuple[str, str]]:
    rows = session.execute(
        text(
            """
            SELECT table_name, privilege_type
            FROM information_schema.role_table_grants
            WHERE grantee = 'findraft'
              AND table_schema = 'public'
            """
        )
    ).all()
    return [(row.table_name, row.privilege_type) for row in rows]


def _restricted_tables(session) -> set[str]:
    rows = session.execute(
        text(
            r"""
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_trigger t ON t.tgrelid = c.oid AND NOT t.tgisinternal
            JOIN pg_proc p ON p.oid = t.tgfoid
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND (
                p.proname LIKE '%append_only'
                OR p.proname LIKE '%\_lines\_immutable' ESCAPE '\'
                OR p.proname = 'findraft_confirmed_mappings_immutable'
              )
            """
        )
    ).all()
    return {row.relname for row in rows} | set(_APPEND_ONLY_WITHOUT_TRIGGER)


def test_provision_script_does_not_regrant_table_all() -> None:
    provision = (
        _BACKEND / "scripts" / "provision_findraft_app_role.sql"
    ).read_text()
    privileges = (_BACKEND / "scripts" / "findraft_table_privileges.sql").read_text()
    code = "\n".join(
        line
        for line in provision.splitlines()
        if not line.strip().startswith("--")
    )
    assert "ON ALL TABLES" not in code
    assert "ON TABLES" not in code
    assert "\\ir findraft_table_privileges.sql" in provision
    assert "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO findraft" in provision
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO findraft" in provision
    assert "REVOKE ALL ON TABLES FROM findraft" in privileges
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO findraft" in privileges
    assert "findraft_tb_versions" not in privileges.split("append_only text[]", 1)[1]


def test_findraft_has_no_dangerous_table_privileges() -> None:
    with SyncSessionLocal() as session:
        grants = _grants(session)
        restricted = _restricted_tables(session)
        version_triggers = session.execute(
            text(
                """
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_trigger t ON t.tgrelid = c.oid AND NOT t.tgisinternal
                JOIN pg_proc p ON p.oid = t.tgfoid
                WHERE n.nspname = 'public'
                  AND p.proname IN (
                    'findraft_tb_versions_immutable',
                    'findraft_fa_versions_immutable'
                  )
                """
            )
        ).all()
    assert {row.relname for row in version_triggers}.isdisjoint(restricted)
    dangerous = [
        (table, privilege)
        for table, privilege in grants
        if privilege in {"TRUNCATE", "REFERENCES", "TRIGGER"}
    ]
    assert dangerous == []
    mutated = [
        (table, privilege)
        for table, privilege in grants
        if table in restricted and privilege in {"UPDATE", "DELETE", "TRUNCATE"}
    ]
    assert mutated == []
    by_table: dict[str, set[str]] = {}
    for table, privilege in grants:
        by_table.setdefault(table, set()).add(privilege)
    for table in restricted:
        assert by_table.get(table) == {"SELECT", "INSERT"}
    for table in _VERSION_TABLES:
        assert "UPDATE" in by_table[table]
        assert "DELETE" in by_table[table]
    # The Stripe webhook sets processed_at on the row it inserted.
    assert by_table["subscription_events"] == {"SELECT", "INSERT", "UPDATE"}


def test_foreign_key_cascade_and_set_null_after_the_revokes(
    provisioned_org: dict,
) -> None:
    """Deleting the trial-balance row still cascades and still clears the pointer.

    findraft has no TRIGGER privilege. The foreign-key actions still run:
    financial_statements disappears (ON DELETE CASCADE) and
    adopted_trial_balance_id becomes null (ON DELETE SET NULL).
    """
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    tb_id = uuid.uuid4()
    statement_id = uuid.uuid4()
    year_end_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        trigger_grant = session.execute(
            text(
                """
                SELECT count(*)
                FROM information_schema.role_table_grants
                WHERE grantee = 'findraft'
                  AND table_schema = 'public'
                  AND table_name IN ('trial_balances', 'findraft_year_ends')
                  AND privilege_type = 'TRIGGER'
                """
            )
        ).scalar_one()
        assert trigger_grant == 0
        session.execute(
            text(
                """
                INSERT INTO trial_balances (
                  id, company_id, period_end, file_url, file_type, status
                ) VALUES (
                  :id, :company, DATE '2024-06-30', :url, 'csv', 'complete'
                )
                """
            ),
            {
                "id": str(tb_id),
                "company": str(company_id),
                "url": f"file:///tmp/{tb_id}.csv",
            },
        )
        session.execute(
            text(
                """
                INSERT INTO financial_statements (
                  id, tb_id, statement_type, data
                ) VALUES (
                  :id, :tb, 'SOPL', '{}'::jsonb
                )
                """
            ),
            {"id": str(statement_id), "tb": str(tb_id)},
        )
        session.execute(
            text(
                """
                INSERT INTO findraft_year_ends (
                  id, org_id, company_id, period_end, pack_id, pack_version,
                  adopted_trial_balance_id
                ) VALUES (
                  :id, :org, :company, DATE '2024-06-30',
                  'frs102-1a-ie', '2024.09', :tb
                )
                """
            ),
            {
                "id": str(year_end_id),
                "org": str(org_id),
                "company": str(company_id),
                "tb": str(tb_id),
            },
        )
        session.commit()

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        visible = session.execute(
            text("SELECT count(*) FROM financial_statements WHERE id = :id"),
            {"id": str(statement_id)},
        ).scalar_one()
        pointer_before = session.execute(
            text(
                """
                SELECT adopted_trial_balance_id
                FROM findraft_year_ends
                WHERE id = :id
                """
            ),
            {"id": str(year_end_id)},
        ).scalar_one()
        assert visible == 1
        assert pointer_before == tb_id
        deleted = session.execute(
            text("DELETE FROM trial_balances WHERE id = :id"),
            {"id": str(tb_id)},
        )
        assert deleted.rowcount == 1
        session.commit()

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        remaining = session.execute(
            text("SELECT count(*) FROM financial_statements WHERE id = :id"),
            {"id": str(statement_id)},
        ).scalar_one()
        pointer = session.execute(
            text(
                """
                SELECT adopted_trial_balance_id
                FROM findraft_year_ends
                WHERE id = :id
                """
            ),
            {"id": str(year_end_id)},
        ).scalar_one()
    assert remaining == 0
    assert pointer is None
