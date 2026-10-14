"""Revision y1z2a3b4c5 adds the comparative source. The model maps it."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db import SyncSessionLocal
from app.services.schema_revision import code_heads
from findraft.models.year_end import YearEnd

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "y1z2a3b4c5_prior_year_comparative_source.py"
)
_MODEL = Path(__file__).resolve().parents[2] / "findraft" / "models" / "year_end.py"
_COLUMNS = (
    "comparative_source",
    "comparative_source_trial_balance_id",
    "comparative_source_year_end_id",
    "comparative_source_draft_id",
    "comparative_source_sha256",
)


def test_migration_adds_the_source_without_a_read_or_grant_all() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "y1z2a3b4c5"' in source
    assert 'down_revision: Union[str, None] = "x0y1z2a3b4"' in source
    model = _MODEL.read_text()
    for name in _COLUMNS:
        assert f"ADD COLUMN {name} " in source
        assert f"DROP COLUMN IF EXISTS {name}" in source
        assert name in YearEnd.__table__.columns
        assert f"{name}:" in model
    assert "findraft_table_privileges.sql" in source
    assert "findraft_year_ends_comparative_source_check" in source
    assert "'product1_tb', 'first_period', 'manual', 'final_snapshot'" in source
    assert "REFERENCES trial_balances (id)" in source
    assert "REFERENCES findraft_year_ends (id)" in source
    assert "ON DELETE SET NULL" in source
    assert "GRANT ALL" not in executable
    assert "SET DEFAULT" not in source
    assert "SELECT" not in executable


def test_code_head_is_the_prior_year_source_revision() -> None:
    assert code_heads() == ("n0o1p2q3r4",)


def test_columns_are_nullable_with_no_server_default() -> None:
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT column_name, is_nullable, column_default, data_type,
                       character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'findraft_year_ends'
                  AND column_name IN (
                    'comparative_source',
                    'comparative_source_trial_balance_id',
                    'comparative_source_year_end_id',
                    'comparative_source_draft_id',
                    'comparative_source_sha256'
                  )
                """
            )
        ).all()
        check = session.execute(
            text(
                """
                SELECT check_clause
                FROM information_schema.check_constraints
                WHERE constraint_schema = 'public'
                  AND constraint_name = 'findraft_year_ends_comparative_source_check'
                """
            )
        ).scalar_one()
        keys = session.execute(
            text(
                """
                SELECT tc.constraint_name, ccu.table_name, rc.delete_rule
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.referential_constraints AS rc
                  ON rc.constraint_schema = tc.constraint_schema
                 AND rc.constraint_name = tc.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_schema = rc.unique_constraint_schema
                 AND ccu.constraint_name = rc.unique_constraint_name
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = 'findraft_year_ends'
                  AND tc.constraint_name IN (
                    'findraft_year_ends_comparative_source_tb_fk',
                    'findraft_year_ends_comparative_source_year_end_fk'
                  )
                """
            )
        ).all()
    found = {row.column_name: row for row in rows}
    assert set(found) == set(_COLUMNS)
    for row in found.values():
        assert row.is_nullable == "YES"
        assert row.column_default is None
    assert found["comparative_source"].data_type == "character varying"
    assert found["comparative_source"].character_maximum_length == 32
    assert found["comparative_source_sha256"].data_type == "character varying"
    assert found["comparative_source_sha256"].character_maximum_length == 64
    for name in (
        "comparative_source_trial_balance_id",
        "comparative_source_year_end_id",
        "comparative_source_draft_id",
    ):
        assert found[name].data_type == "uuid"
    clause = check.replace(" ", "")
    for value in ("product1_tb", "first_period", "manual", "final_snapshot"):
        assert value in clause
    linked = {row.constraint_name: row for row in keys}
    assert linked["findraft_year_ends_comparative_source_tb_fk"].table_name == (
        "trial_balances"
    )
    assert linked[
        "findraft_year_ends_comparative_source_year_end_fk"
    ].table_name == "findraft_year_ends"
    assert {row.delete_rule for row in keys} == {"SET NULL"}
