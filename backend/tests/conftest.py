"""Shared pytest fixtures — real Postgres, JWT helpers, ASGI client."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta, timezone
from io import BytesIO

import jwt
import openpyxl
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db import SyncSessionLocal, set_rls_org_id
from app.main import app
from app.models.client import Client
from app.models.company import Company
from app.services.org_provisioning import (
    organisation_id_for_clerk_org,
    provision_first_signup,
)


_owner_engine = None


def open_owner_session() -> Session:
    """Session that can disable triggers.

    The production API logs in as ``findraft``, which is not the table owner,
    so ``ALTER TABLE ... DISABLE TRIGGER`` fails for that login. Set
    ``DATABASE_OWNER_URL`` to the superuser that ran migrations. When it is
    unset, this is the same session the rest of the suite uses.
    """
    global _owner_engine
    owner_url = os.environ.get("DATABASE_OWNER_URL")
    if not owner_url:
        return SyncSessionLocal()
    if _owner_engine is None:
        _owner_engine = create_engine(owner_url, pool_pre_ping=True)
    factory = sessionmaker(
        bind=_owner_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    return factory()


# Privileges the application login does not have, and this cleanup needs.
# UPDATE covers SELECT ... FOR KEY SHARE on a foreign key. DELETE covers
# the row and ON DELETE CASCADE. subscription_events already has UPDATE.
_CLEANUP_GRANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("archived_records", ("UPDATE", "DELETE")),
    ("audit_logs", ("UPDATE", "DELETE")),
    ("findraft_draft_operations", ("UPDATE", "DELETE")),
    ("findraft_tb_lines", ("UPDATE", "DELETE")),
    ("findraft_fa_lines", ("UPDATE", "DELETE")),
    ("findraft_confirmed_mappings", ("UPDATE", "DELETE")),
    ("subscription_events", ("DELETE",)),
)


def _grant_append_only_delete(session: Session) -> tuple[tuple[str, str], ...]:
    """Grant missing cleanup privileges. A superuser needs no grant."""
    granted: list[tuple[str, str]] = []
    for table, privileges in _CLEANUP_GRANTS:
        for privilege in privileges:
            allowed = session.execute(
                text("SELECT has_table_privilege(current_user, :table, :privilege)"),
                {"table": table, "privilege": privilege},
            ).scalar_one()
            if not allowed:
                session.execute(
                    text(f"GRANT {privilege} ON TABLE {table} TO CURRENT_USER")
                )
                granted.append((table, privilege))
    return tuple(granted)


def _revoke_append_only_delete(
    session: Session, granted: tuple[tuple[str, str], ...]
) -> None:
    """Drop only the privileges this cleanup granted."""
    for table, privilege in granted:
        session.execute(text(f"REVOKE {privilege} ON TABLE {table} FROM CURRENT_USER"))
        cleared = session.execute(
            text(
                "SELECT rolsuper OR rolbypassrls OR NOT has_table_privilege("
                "current_user, :table, :privilege) "
                "FROM pg_roles WHERE rolname = current_user"
            ),
            {"table": table, "privilege": privilege},
        ).scalar_one()
        if not cleared:
            raise RuntimeError(f"{privilege} grant left on {table}")


def _delete_append_only(
    session: Session, table: str, clause: str, params: dict[str, str]
) -> None:
    """Delete rows the application login is not granted to delete.

    ``archived_records`` and the other append-only tables grant ``findraft``
    ``SELECT`` and ``INSERT`` only. The table owner still has the grant
    option, so this cleanup grants ``DELETE`` to the current user, deletes
    the rows, and revokes ``DELETE`` before the transaction commits. A
    superuser deletes directly. The privilege script is not changed.
    """
    if not table.replace("_", "").isalnum():
        raise ValueError(table)
    statement = text(f"DELETE FROM {table} WHERE {clause}")
    savepoint = session.begin_nested()
    try:
        session.execute(statement, params)
        savepoint.commit()
    except ProgrammingError as exc:
        savepoint.rollback()
        if getattr(exc.orig, "pgcode", None) != "42501":
            raise
        session.execute(text(f"GRANT DELETE ON TABLE {table} TO CURRENT_USER"))
        session.execute(statement, params)
        session.execute(text(f"REVOKE DELETE ON TABLE {table} FROM CURRENT_USER"))
        still = session.execute(
            text(
                "SELECT rolsuper OR rolbypassrls OR NOT has_table_privilege("
                "current_user, :table, 'DELETE') "
                "FROM pg_roles WHERE rolname = current_user"
            ),
            {"table": table},
        ).scalar_one()
        if not still:
            raise RuntimeError(f"DELETE grant left on {table}")


@pytest.fixture(scope="session", autouse=True)
def _force_rls_on_all_tables() -> None:
    """Ensure FORCE ROW LEVEL SECURITY is on (migration a1b2c3d4e5f6)."""
    tables = (
        "clients",
        "audit_logs",
        "notifications",
        "archived_records",
        "users",
        "subscription_events",
        "organisations",
        "companies",
        "trial_balances",
        "account_mappings",
        "financial_statements",
        "variance_analyses",
        "risk_flags",
        "exports",
        "processing_jobs",
        "statement_line_items",
        "commentary_feedback",
        "waitlist_signups",
        "findraft_year_ends",
        "findraft_draft_versions",
        "findraft_source_documents",
        "findraft_tb_versions",
        "findraft_tb_lines",
        "findraft_prior_year_lines",
        "findraft_fa_versions",
        "findraft_fa_lines",
        "findraft_confirmed_mappings",
        "findraft_adjustment_journals",
        "findraft_adjustment_lines",
        "findraft_disclosure_answers",
        "findraft_draft_operations",
        "findraft_render_jobs",
    )
    with open_owner_session() as session:
        for table in tables:
            session.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        session.commit()


@pytest.fixture(autouse=True)
def _patch_request_auth_to_test_hs256(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route request auth through HS256 test tokens for the ASGI suite only.

    Production ``decode_access_token`` is RS256/Clerk JWKS only. Tests mint
    HS256 tokens via ``make_access_token`` and swap the entry point here so
    ``get_auth_context`` never needs a live JWKS. This patch does not exist
    outside pytest.
    """
    from app.dependencies import decode_test_hs256_token

    monkeypatch.setattr(
        "app.dependencies.decode_access_token",
        decode_test_hs256_token,
    )


@pytest.fixture(autouse=True)
def _product2_import_stays_pending_until_the_test_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP import returns 202 pending. Parsing is a separate worker.

    Production queues that worker after the response. This suite calls
    ``process_tb_version`` itself and asserts the row is still pending, so
    the background hook stays off unless a test turns it back on.
    """
    monkeypatch.setattr(settings, "tb_import_background", False)


@pytest.fixture(autouse=True)
def _tests_skip_clerk_webhook_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsigned Clerk webhook fixtures skip verification in development only.

    ``backend/.env`` may set ``CLERK_WEBHOOK_SECRET`` for local deploy testing.
    When the secret is present, ``/auth/webhook`` requires Svix headers even if
    ``APP_ENV=development``. Tests POST unsigned JSON fixtures — clear the secret
    so they exercise provisioning logic, not HMAC wiring (see test_auth.py).
    """
    monkeypatch.setattr(settings, "clerk_webhook_secret", None)


def make_access_token(
    *,
    clerk_user_id: str,
    clerk_org_id: str,
    role: str = "owner",
    org_uuid: uuid.UUID | None = None,
) -> str:
    org_id = org_uuid or organisation_id_for_clerk_org(clerk_org_id)
    payload = {
        "sub": clerk_user_id,
        "org_id": clerk_org_id,
        "org_uuid": str(org_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(
        payload, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm
    )


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def balanced_tb_xlsx_bytes() -> bytes:
    """Closed-books TB that passes tb_integrity, balance_sheet_balance, and net_assets."""
    workbook = openpyxl.Workbook()
    ws = workbook.active
    ws.append(["Account Code", "Account Name", "Debit", "Credit"])
    ws.append(["1100", "Cash at bank", "10000.00", "0.00"])
    ws.append(["3100", "Retained earnings", "0.00", "6000.00"])
    ws.append(["3000", "Share capital", "0.00", "4000.00"])
    # P&L lines that net to zero so SOPL is non-empty but BS still balances.
    ws.append(["4100", "Sales - Online", "0.00", "5000.00"])
    ws.append(["6100", "Operating expenses", "5000.00", "0.00"])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def provisioned_org() -> Iterator[dict]:
    """Create org+owner via the real RLS bootstrap; yield ids; clean up after."""
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_test_{suffix}"
    clerk_user_id = f"user_test_{suffix}"
    with SyncSessionLocal() as session:
        provisioned = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name=f"Test Org {suffix}",
            clerk_user_id=clerk_user_id,
            email=f"owner-{suffix}@example.com",
            role="owner",
        )
        set_rls_org_id(session, provisioned.organisation.id)
        provisioned.organisation.letterhead_address = "1 Practice Quay\nDublin"
        provisioned.organisation.letterhead_contact = "01 555 0100"
        client = Client(
            org_id=provisioned.organisation.id,
            name=f"Client {suffix}",
        )
        session.add(client)
        session.flush()
        company = Company(
            client_id=client.id,
            name=f"Company {suffix} Limited",
            functional_currency="GBP",
            # The shared fixture is an Irish company so the Irish pack tests
            # stay on today's path. A company created without this field is NULL.
            country_of_incorporation="IE",
        )
        session.add(company)
        session.commit()
        data = {
            "org_id": provisioned.organisation.id,
            "user_id": provisioned.user.id,
            "client_id": client.id,
            "company_id": company.id,
            "clerk_org_id": clerk_org_id,
            "clerk_user_id": clerk_user_id,
            "token": make_access_token(
                clerk_user_id=clerk_user_id,
                clerk_org_id=clerk_org_id,
                org_uuid=provisioned.organisation.id,
            ),
        }
    yield data
    with open_owner_session() as session:
        set_rls_org_id(session, data["org_id"])
        granted_deletes = _grant_append_only_delete(session)
        session.execute(
            text(
                "DELETE FROM statement_line_items WHERE statement_id IN "
                "(SELECT id FROM financial_statements WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid))))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM financial_statements WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM commentary_feedback WHERE variance_id IN "
                "(SELECT id FROM variance_analyses WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid))))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM variance_analyses WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM risk_flags WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM exports WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM processing_jobs WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM account_mappings WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid))"
            ),
            {"oid": str(data["org_id"])},
        )
        _delete_append_only(
            session, "archived_records", "org_id = :oid", {"oid": str(data["org_id"])}
        )
        session.execute(
            text(
                "DELETE FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "ALTER TABLE findraft_prior_year_lines "
                "DISABLE TRIGGER findraft_prior_year_lines_locked"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_confirmed_mappings "
                "DISABLE TRIGGER findraft_confirmed_mappings_immutable"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_adjustment_journals "
                "DISABLE TRIGGER findraft_adjustment_journals_locked_draft"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_adjustment_lines "
                "DISABLE TRIGGER findraft_adjustment_lines_locked_draft"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_adjustment_lines "
                "DISABLE TRIGGER findraft_adjustment_journal_must_balance"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_disclosure_answers "
                "DISABLE TRIGGER findraft_disclosure_answers_locked_draft"
            )
        )
        session.execute(
            text(
                "ALTER TABLE audit_logs DISABLE TRIGGER findraft_audit_log_append_only"
            )
        )
        _delete_append_only(
            session, "audit_logs", "org_id = :oid", {"oid": str(data["org_id"])}
        )
        session.execute(
            text("DELETE FROM findraft_render_jobs WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        _delete_append_only(
            session,
            "findraft_draft_operations",
            "org_id = :oid",
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM findraft_adjustment_lines WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM findraft_adjustment_journals WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM findraft_disclosure_answers WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        _delete_append_only(
            session,
            "findraft_confirmed_mappings",
            "org_id = :oid",
            {"oid": str(data["org_id"])},
        )
        _delete_append_only(
            session, "findraft_fa_lines", "org_id = :oid", {"oid": str(data["org_id"])}
        )
        session.execute(
            text("DELETE FROM findraft_fa_versions WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        _delete_append_only(
            session, "findraft_tb_lines", "org_id = :oid", {"oid": str(data["org_id"])}
        )
        session.execute(
            text("DELETE FROM findraft_draft_versions WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM findraft_tb_versions WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM findraft_prior_year_lines WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM findraft_year_ends WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "ALTER TABLE findraft_confirmed_mappings "
                "ENABLE TRIGGER findraft_confirmed_mappings_immutable"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_prior_year_lines "
                "ENABLE TRIGGER findraft_prior_year_lines_locked"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_adjustment_journals "
                "ENABLE TRIGGER findraft_adjustment_journals_locked_draft"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_adjustment_lines "
                "ENABLE TRIGGER findraft_adjustment_lines_locked_draft"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_adjustment_lines "
                "ENABLE TRIGGER findraft_adjustment_journal_must_balance"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_disclosure_answers "
                "ENABLE TRIGGER findraft_disclosure_answers_locked_draft"
            )
        )
        session.execute(
            text("DELETE FROM findraft_source_documents WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM clients WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM notifications WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM users WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM subscription_events WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("ALTER TABLE audit_logs ENABLE TRIGGER findraft_audit_log_append_only")
        )
        _revoke_append_only_delete(session, granted_deletes)
        session.commit()


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
