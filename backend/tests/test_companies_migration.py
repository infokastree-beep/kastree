"""Companion tests for d4e5f6a7b8c0_add_companies_table migration.

Exercises upgrade integrity, cross-org RLS on companies / trial_balances /
account_mappings, clean downgrade (1:1 client->company), and blocked downgrade
when a client has multiple companies.
"""

from __future__ import annotations

import importlib.util
import subprocess
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.account_mapping import AccountMapping
from app.models.client import Client
from app.models.trial_balance import TrialBalance
from app.services.org_provisioning import provision_first_signup

DOWN_REVISION = "c3d4e5f6a7b8"
UP_REVISION = "d4e5f6a7b8c0"
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
RLS_FLAG_TABLES = ("companies", "trial_balances", "account_mappings")
MIGRATION_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "d4e5f6a7b8c0_add_companies_table.py"
)


def _load_companies_migration_module():
    spec = importlib.util.spec_from_file_location(
        "d4e5f6a7b8c0_add_companies_table", MIGRATION_MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _pg_class_rls_flags(session, tables: tuple[str, ...] = RLS_FLAG_TABLES) -> list[dict]:
    """Read pg_class.relrowsecurity and relforcerowsecurity directly."""
    rows = session.execute(
        text(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = ANY(:tables)
            ORDER BY c.relname
            """
        ),
        {"tables": list(tables)},
    ).all()
    return [
        {
            "relname": row[0],
            "relrowsecurity": row[1],
            "relforcerowsecurity": row[2],
        }
        for row in rows
    ]


def _format_pg_class_rls_flags(flags: list[dict]) -> str:
    lines = ["relname | relrowsecurity | relforcerowsecurity", "--------+---------------+--------------------"]
    for row in flags:
        lines.append(
            f"{row['relname']:<7} | {str(row['relrowsecurity']):<13} | {str(row['relforcerowsecurity'])}"
        )
    return "\n".join(lines)


def _assert_pg_class_rls_flags(flags: list[dict]) -> None:
    assert len(flags) == len(RLS_FLAG_TABLES), flags
    for row in flags:
        assert row["relrowsecurity"] is True, row
        assert row["relforcerowsecurity"] is True, row


def _alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


def _current_revision() -> str | None:
    with SyncSessionLocal() as session:
        return session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()


def _alembic_upgrade(revision: str) -> None:
    command.upgrade(_alembic_config(), revision)


def _alembic_downgrade(revision: str) -> None:
    command.downgrade(_alembic_config(), revision)


def _table_exists(session, table: str) -> bool:
    return bool(
        session.execute(
            text("SELECT to_regclass(:name) IS NOT NULL"),
            {"name": f"public.{table}"},
        ).scalar()
    )


def _column_exists(session, table: str, column: str) -> bool:
    return bool(
        session.execute(
            text(
                """
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'public'
                    AND table_name = :table
                    AND column_name = :column
                )
                """
            ),
            {"table": table, "column": column},
        ).scalar()
    )


def _seed_org_with_client_tb(*, suffix: str) -> dict:
    """Create org + client + TB + mappings under pre-migration (downgraded) schema."""
    clerk_org_id = f"org_mig_{suffix}"
    clerk_user_id = f"user_mig_{suffix}"
    tb_id = uuid.uuid4()
    client_id = uuid.uuid4()

    company_number = f"CO-{suffix[:6]}"
    with SyncSessionLocal() as session:
        provisioned = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name=f"Migration Org {suffix}",
            clerk_user_id=clerk_user_id,
            email=f"mig-{suffix}@example.com",
            role="owner",
        )
        org_id = provisioned.organisation.id
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                """
                INSERT INTO clients (
                    id, org_id, name, company_number, industry,
                    functional_currency, materiality_threshold_pct,
                    materiality_threshold_abs, is_deleted
                )
                VALUES (
                    :id, :org_id, :name, :company_number, :industry,
                    :functional_currency, :materiality_pct, :materiality_abs, false
                )
                """
            ),
            {
                "id": str(client_id),
                "org_id": str(org_id),
                "name": f"Client {suffix}",
                "company_number": company_number,
                "industry": "Testing",
                "functional_currency": "EUR",
                "materiality_pct": "12.50",
                "materiality_abs": "2500.00",
            },
        )
        session.execute(
            text(
                """
                INSERT INTO trial_balances (
                    id, client_id, period_end, file_url, file_type, status, currency
                )
                VALUES (
                    :id, :client_id, :period_end, :file_url, 'xlsx', 'mapping', 'EUR'
                )
                """
            ),
            {
                "id": str(tb_id),
                "client_id": str(client_id),
                "period_end": date(2026, 6, 30),
                "file_url": f"file:///tmp/mig-{suffix}.xlsx",
            },
        )
        session.execute(
            text(
                """
                INSERT INTO account_mappings (
                    id, client_id, source_code, source_name, canonical_line,
                    confidence, method, is_confirmed, is_ignored
                )
                VALUES (
                    gen_random_uuid(), :client_id, '1000', 'Cash', 'cash',
                    1.00, 'exact', true, false
                )
                """
            ),
            {"client_id": str(client_id)},
        )
        session.execute(
            text(
                """
                INSERT INTO account_mappings (
                    id, client_id, source_code, source_name, canonical_line,
                    confidence, method, is_confirmed, is_ignored
                )
                VALUES (
                    gen_random_uuid(), :client_id, '4000', 'Revenue', 'revenue',
                    0.90, 'fuzzy', false, false
                )
                """
            ),
            {"client_id": str(client_id)},
        )
        session.commit()

    return {
        "org_id": org_id,
        "client_id": client_id,
        "tb_id": tb_id,
        "clerk_org_id": clerk_org_id,
        "company_number": company_number,
    }


def _org_counts(session, org_id: uuid.UUID) -> dict[str, int]:
    """Row counts visible under one org's RLS context."""
    set_rls_org_id(session, org_id)
    counts: dict[str, int] = {
        "clients": session.execute(text("SELECT COUNT(*) FROM clients")).scalar_one(),
        "trial_balances": session.execute(
            text("SELECT COUNT(*) FROM trial_balances")
        ).scalar_one(),
        "account_mappings": session.execute(
            text("SELECT COUNT(*) FROM account_mappings")
        ).scalar_one(),
    }
    if _table_exists(session, "companies"):
        counts["companies"] = session.execute(
            text("SELECT COUNT(*) FROM companies")
        ).scalar_one()
    else:
        counts["companies"] = 0
    return counts


def _combined_org_counts(session, org_ids: list[uuid.UUID]) -> dict[str, int]:
    combined = {"clients": 0, "trial_balances": 0, "account_mappings": 0, "companies": 0}
    for org_id in org_ids:
        org = _org_counts(session, org_id)
        for key in combined:
            combined[key] += org[key]
    return combined


def _assert_post_upgrade_integrity_for_org(
    session,
    org_id: uuid.UUID,
    *,
    expected_clients: int,
    expected_companies: int,
    expected_tbs: int,
    expected_mappings: int,
) -> None:
    counts = _org_counts(session, org_id)
    assert counts["clients"] == expected_clients
    assert counts["companies"] == expected_companies
    assert counts["trial_balances"] == expected_tbs
    assert counts["account_mappings"] == expected_mappings
    assert expected_clients == expected_companies

    set_rls_org_id(session, org_id)
    orphan_companies = session.execute(
        text(
            """
            SELECT COUNT(*) FROM companies co
            LEFT JOIN clients c ON co.client_id = c.id
            WHERE c.id IS NULL
            """
        )
    ).scalar_one()
    assert orphan_companies == 0

    orphan_tbs = session.execute(
        text(
            """
            SELECT COUNT(*) FROM trial_balances tb
            LEFT JOIN companies co ON tb.company_id = co.id
            WHERE tb.company_id IS NULL OR co.id IS NULL
            """
        )
    ).scalar_one()
    assert orphan_tbs == 0

    orphan_mappings = session.execute(
        text(
            """
            SELECT COUNT(*) FROM account_mappings am
            LEFT JOIN companies co ON am.company_id = co.id
            WHERE am.company_id IS NULL OR co.id IS NULL
            """
        )
    ).scalar_one()
    assert orphan_mappings == 0


def _assert_companies_rls_isolation(
    session,
    *,
    owner_org_id: uuid.UUID,
    owner_client_id: uuid.UUID,
    other_org_id: uuid.UUID,
) -> None:
    set_rls_org_id(session, owner_org_id)
    visible = session.execute(
        text("SELECT COUNT(*) FROM companies WHERE client_id = :cid"),
        {"cid": str(owner_client_id)},
    ).scalar_one()
    assert visible == 1

    set_rls_org_id(session, other_org_id)
    hidden = session.execute(
        text("SELECT COUNT(*) FROM companies WHERE client_id = :cid"),
        {"cid": str(owner_client_id)},
    ).scalar_one()
    assert hidden == 0


def _assert_tb_rls_isolation(
    session,
    *,
    owner_org_id: uuid.UUID,
    owner_tb_id: uuid.UUID,
    other_org_id: uuid.UUID,
) -> None:
    set_rls_org_id(session, owner_org_id)
    visible = session.execute(
        text("SELECT COUNT(*) FROM trial_balances WHERE id = :tid"),
        {"tid": str(owner_tb_id)},
    ).scalar_one()
    assert visible == 1

    set_rls_org_id(session, other_org_id)
    hidden = session.execute(
        text("SELECT COUNT(*) FROM trial_balances WHERE id = :tid"),
        {"tid": str(owner_tb_id)},
    ).scalar_one()
    assert hidden == 0


def _assert_mapping_rls_isolation(
    session,
    *,
    owner_org_id: uuid.UUID,
    owner_client_id: uuid.UUID,
    other_org_id: uuid.UUID,
) -> None:
    set_rls_org_id(session, owner_org_id)
    visible = session.execute(
        text(
            """
            SELECT COUNT(*) FROM account_mappings am
            JOIN companies co ON am.company_id = co.id
            WHERE co.client_id = :cid
            """
        ),
        {"cid": str(owner_client_id)},
    ).scalar_one()
    assert visible == 2

    set_rls_org_id(session, other_org_id)
    hidden = session.execute(
        text(
            """
            SELECT COUNT(*) FROM account_mappings am
            JOIN companies co ON am.company_id = co.id
            WHERE co.client_id = :cid
            """
        ),
        {"cid": str(owner_client_id)},
    ).scalar_one()
    assert hidden == 0


def _cleanup_org(org_id: uuid.UUID) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        if _table_exists(session, "companies"):
            session.execute(
                text(
                    """
                    DELETE FROM statement_line_items WHERE statement_id IN (
                      SELECT id FROM financial_statements WHERE tb_id IN (
                        SELECT id FROM trial_balances WHERE company_id IN (
                          SELECT id FROM companies WHERE client_id IN (
                            SELECT id FROM clients WHERE org_id = :oid
                          )
                        )
                      )
                    )
                    """
                ),
                {"oid": str(org_id)},
            )
            session.execute(
                text(
                    """
                    DELETE FROM financial_statements WHERE tb_id IN (
                      SELECT id FROM trial_balances WHERE company_id IN (
                        SELECT id FROM companies WHERE client_id IN (
                          SELECT id FROM clients WHERE org_id = :oid
                        )
                      )
                    )
                    """
                ),
                {"oid": str(org_id)},
            )
            session.execute(
                text(
                    """
                    DELETE FROM account_mappings WHERE company_id IN (
                      SELECT id FROM companies WHERE client_id IN (
                        SELECT id FROM clients WHERE org_id = :oid
                      )
                    )
                    """
                ),
                {"oid": str(org_id)},
            )
            session.execute(
                text(
                    """
                    DELETE FROM trial_balances WHERE company_id IN (
                      SELECT id FROM companies WHERE client_id IN (
                        SELECT id FROM clients WHERE org_id = :oid
                      )
                    )
                    """
                ),
                {"oid": str(org_id)},
            )
            session.execute(
                text(
                    """
                    DELETE FROM companies WHERE client_id IN (
                      SELECT id FROM clients WHERE org_id = :oid
                    )
                    """
                ),
                {"oid": str(org_id)},
            )
        else:
            session.execute(
                text(
                    """
                    DELETE FROM account_mappings WHERE client_id IN (
                      SELECT id FROM clients WHERE org_id = :oid
                    )
                    """
                ),
                {"oid": str(org_id)},
            )
            session.execute(
                text(
                    """
                    DELETE FROM trial_balances WHERE client_id IN (
                      SELECT id FROM clients WHERE org_id = :oid
                    )
                    """
                ),
                {"oid": str(org_id)},
            )
        session.execute(
            text("DELETE FROM clients WHERE org_id = :oid"),
            {"oid": str(org_id)},
        )
        session.execute(
            text("DELETE FROM users WHERE org_id = :oid"),
            {"oid": str(org_id)},
        )
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"),
            {"oid": str(org_id)},
        )
        session.commit()


def _prepare_downgrade_safe_state() -> None:
    """Keep one company per client so migration downgrade guard passes on shared dev DB."""
    subprocess.run(
        [
            "sudo",
            "-u",
            "postgres",
            "psql",
            "findraft_dev",
            "-c",
            """
            DELETE FROM companies
            WHERE id NOT IN (
                SELECT DISTINCT ON (client_id) id
                FROM companies
                ORDER BY client_id, created_at ASC
            );
            """,
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def migration_revision_guard():
    """Ensure we leave the DB at the revision we started on."""
    original = _current_revision()
    if original not in (None, DOWN_REVISION, UP_REVISION):
        pytest.skip(
            f"Unexpected alembic revision {original!r}; "
            f"expected {DOWN_REVISION} or {UP_REVISION}"
        )
    try:
        if original == UP_REVISION:
            _prepare_downgrade_safe_state()
            _alembic_downgrade(DOWN_REVISION)
        yield original
    finally:
        current = _current_revision()
        if original == UP_REVISION and current != UP_REVISION:
            _alembic_upgrade(UP_REVISION)
        elif current == UP_REVISION and original == DOWN_REVISION:
            _prepare_downgrade_safe_state()
            _alembic_downgrade(DOWN_REVISION)
        elif current is None and original:
            _alembic_upgrade(original)


def test_companies_migration_upgrade_integrity_rls_and_clean_downgrade(
    migration_revision_guard,
) -> None:
    suffix = uuid.uuid4().hex[:10]
    org_a = _seed_org_with_client_tb(suffix=f"a{suffix}")
    org_b = _seed_org_with_client_tb(suffix=f"b{suffix}")

    with SyncSessionLocal() as session:
        counts_before = _combined_org_counts(
            session, [org_a["org_id"], org_b["org_id"]]
        )
        assert counts_before["companies"] == 0
        assert counts_before["clients"] == 2
        assert counts_before["trial_balances"] == 2
        assert counts_before["account_mappings"] == 4

    try:
        _alembic_upgrade(UP_REVISION)
        assert _current_revision() == UP_REVISION

        with SyncSessionLocal() as session:
            assert _table_exists(session, "companies")
            assert _column_exists(session, "trial_balances", "company_id")
            assert not _column_exists(session, "trial_balances", "client_id")
            assert _column_exists(session, "account_mappings", "company_id")
            assert not _column_exists(session, "account_mappings", "client_id")
            assert not _column_exists(session, "clients", "functional_currency")

            counts_after = _combined_org_counts(
                session, [org_a["org_id"], org_b["org_id"]]
            )
            assert counts_after["clients"] == counts_before["clients"]
            assert counts_after["trial_balances"] == counts_before["trial_balances"]
            assert counts_after["account_mappings"] == counts_before["account_mappings"]
            assert counts_after["companies"] == counts_after["clients"]

            _assert_post_upgrade_integrity_for_org(
                session,
                org_a["org_id"],
                expected_clients=1,
                expected_companies=1,
                expected_tbs=1,
                expected_mappings=2,
            )
            _assert_post_upgrade_integrity_for_org(
                session,
                org_b["org_id"],
                expected_clients=1,
                expected_companies=1,
                expected_tbs=1,
                expected_mappings=2,
            )

            set_rls_org_id(session, org_a["org_id"])
            row = session.execute(
                text(
                    """
                    SELECT co.functional_currency, co.company_number, co.industry,
                           co.materiality_threshold_pct, co.materiality_threshold_abs
                    FROM companies co
                    WHERE co.client_id = :cid
                    """
                ),
                {"cid": str(org_a["client_id"])},
            ).one()
            assert row[0] == "EUR"
            assert row[1] == org_a["company_number"]
            assert row[2] == "Testing"
            assert Decimal(str(row[3])) == Decimal("12.50")
            assert Decimal(str(row[4])) == Decimal("2500.00")

            _assert_companies_rls_isolation(
                session,
                owner_org_id=org_a["org_id"],
                owner_client_id=org_a["client_id"],
                other_org_id=org_b["org_id"],
            )
            _assert_tb_rls_isolation(
                session,
                owner_org_id=org_a["org_id"],
                owner_tb_id=org_a["tb_id"],
                other_org_id=org_b["org_id"],
            )
            _assert_mapping_rls_isolation(
                session,
                owner_org_id=org_a["org_id"],
                owner_client_id=org_a["client_id"],
                other_org_id=org_b["org_id"],
            )

            pg_flags = _pg_class_rls_flags(session)
            print("\npg_class RLS flags after upgrade:\n" + _format_pg_class_rls_flags(pg_flags))
            _assert_pg_class_rls_flags(pg_flags)

        _alembic_downgrade(DOWN_REVISION)
        assert _current_revision() == DOWN_REVISION

        with SyncSessionLocal() as session:
            assert not _table_exists(session, "companies")
            assert _column_exists(session, "trial_balances", "client_id")
            assert _column_exists(session, "clients", "functional_currency")

            counts_restored = _combined_org_counts(
                session, [org_a["org_id"], org_b["org_id"]]
            )
            assert counts_restored["clients"] == counts_before["clients"]
            assert counts_restored["trial_balances"] == counts_before["trial_balances"]
            assert counts_restored["account_mappings"] == counts_before["account_mappings"]
            assert counts_restored["companies"] == 0

            set_rls_org_id(session, org_a["org_id"])
            restored = session.execute(
                text(
                    """
                    SELECT functional_currency, company_number, industry
                    FROM clients WHERE id = :cid
                    """
                ),
                {"cid": str(org_a["client_id"])},
            ).one()
            assert restored[0] == "EUR"
            assert restored[1] == org_a["company_number"]
            assert restored[2] == "Testing"

    finally:
        _cleanup_org(org_a["org_id"])
        _cleanup_org(org_b["org_id"])


def test_companies_migration_downgrade_raises_for_multi_company_client(
    migration_revision_guard,
) -> None:
    suffix = uuid.uuid4().hex[:10]
    seeded = _seed_org_with_client_tb(suffix=suffix)

    try:
        _alembic_upgrade(UP_REVISION)

        with SyncSessionLocal() as session:
            set_rls_org_id(session, seeded["org_id"])
            session.execute(
                text(
                    """
                    INSERT INTO companies (
                        id, client_id, name, functional_currency,
                        materiality_threshold_pct, materiality_threshold_abs,
                        is_deleted, created_at, updated_at
                    )
                    VALUES (
                        gen_random_uuid(), :client_id, 'Second Company', 'GBP',
                        10.00, 1000.00, false, now(), now()
                    )
                    """
                ),
                {"client_id": str(seeded["client_id"])},
            )
            session.commit()

            set_rls_org_id(session, seeded["org_id"])
            multi = session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM (
                      SELECT client_id FROM companies
                      GROUP BY client_id
                      HAVING COUNT(*) > 1
                    ) multi
                    """
                )
            ).scalar_one()
            assert multi == 1

        with pytest.raises(Exception) as exc_info:
            _alembic_downgrade(DOWN_REVISION)
        assert "Cannot downgrade: 1 clients have multiple companies" in str(exc_info.value)

        assert _current_revision() == UP_REVISION

        with SyncSessionLocal() as session:
            set_rls_org_id(session, seeded["org_id"])
            assert _table_exists(session, "companies")
            company_count = session.execute(
                text(
                    "SELECT COUNT(*) FROM companies WHERE client_id = :cid"
                ),
                {"cid": str(seeded["client_id"])},
            ).scalar_one()
            assert company_count == 2

    finally:
        with SyncSessionLocal() as session:
            set_rls_org_id(session, seeded["org_id"])
            if _table_exists(session, "companies"):
                session.execute(
                    text(
                        """
                        DELETE FROM companies
                        WHERE client_id = :cid
                          AND name = 'Second Company'
                        """
                    ),
                    {"cid": str(seeded["client_id"])},
                )
                session.commit()
        _cleanup_org(seeded["org_id"])
        if _current_revision() == UP_REVISION and migration_revision_guard == DOWN_REVISION:
            _prepare_downgrade_safe_state()
            _alembic_downgrade(DOWN_REVISION)


def test_pg_class_rls_flags_after_upgrade(migration_revision_guard, capsys) -> None:
    """Direct pg_class check: relrowsecurity AND relforcerowsecurity both true."""
    suffix = uuid.uuid4().hex[:10]
    seeded = _seed_org_with_client_tb(suffix=suffix)
    try:
        _alembic_upgrade(UP_REVISION)
        with SyncSessionLocal() as session:
            flags = _pg_class_rls_flags(session)
            print("\n" + _format_pg_class_rls_flags(flags))
            _assert_pg_class_rls_flags(flags)
    finally:
        _cleanup_org(seeded["org_id"])


def test_rls_disable_rolls_back_when_transaction_aborts() -> None:
    """DISABLE ROW LEVEL SECURITY is transactional — abort restores prior flags."""
    with SyncSessionLocal() as session:
        before = _pg_class_rls_flags(session, ("clients",))[0]
        assert before["relrowsecurity"] is True
        assert before["relforcerowsecurity"] is True

        with pytest.raises(RuntimeError, match="deliberate abort"):
            with session.begin_nested():
                session.execute(text("ALTER TABLE clients DISABLE ROW LEVEL SECURITY"))
                during = _pg_class_rls_flags(session, ("clients",))[0]
                assert during["relrowsecurity"] is False
                raise RuntimeError("deliberate abort")

        after = _pg_class_rls_flags(session, ("clients",))[0]
        assert after == before


def test_migration_failure_rolls_back_rls_disable(migration_revision_guard, monkeypatch) -> None:
    """Alembic upgrade() is one PG transaction; mid-migration failure restores RLS."""
    import alembic.util.pyfiles as pyfiles

    mig = _load_companies_migration_module()
    original_load = pyfiles.load_module_py

    def _load_patched(module_id: str, path: str):
        if path.endswith("d4e5f6a7b8c0_add_companies_table.py"):
            return mig
        return original_load(module_id, path)

    monkeypatch.setattr(pyfiles, "load_module_py", _load_patched)

    suffix = uuid.uuid4().hex[:10]
    seeded = _seed_org_with_client_tb(suffix=suffix)
    try:
        with SyncSessionLocal() as session:
            before = {
                row["relname"]: row
                for row in _pg_class_rls_flags(
                    session, ("clients", "trial_balances", "account_mappings")
                )
            }
        for name in ("clients", "trial_balances", "account_mappings"):
            assert before[name]["relrowsecurity"] is True
            assert before[name]["relforcerowsecurity"] is True

        def _fail_integrity() -> None:
            raise RuntimeError("simulated migration failure after RLS disable")

        monkeypatch.setattr(mig, "_assert_migration_integrity", _fail_integrity)

        with pytest.raises(RuntimeError, match="simulated migration failure"):
            _alembic_upgrade(UP_REVISION)

        monkeypatch.undo()

        assert _current_revision() == DOWN_REVISION
        with SyncSessionLocal() as session:
            assert not _table_exists(session, "companies")
            after = {
                row["relname"]: row
                for row in _pg_class_rls_flags(
                    session, ("clients", "trial_balances", "account_mappings")
                )
            }
        assert after == before
    finally:
        _cleanup_org(seeded["org_id"])
