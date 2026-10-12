"""Revision q3r4s5t6u7 adds nullable size inputs and does not read them."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db import SyncSessionLocal
from app.services.schema_revision import code_heads

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "q3r4s5t6u7_size_inputs.py"
)
_MODEL = Path(__file__).resolve().parents[2] / "findraft" / "models" / "year_end.py"
_SIZE = (
    Path(__file__).resolve().parents[1] / "app" / "services" / "size_eligibility.py"
)
_PACK = (
    Path(__file__).resolve().parents[2]
    / "findraft"
    / "content"
    / "frs102-1a-ie"
    / "2024.09"
    / "pack.json"
)
_COLUMNS = (
    "size_current_turnover",
    "size_current_balance_sheet",
    "size_current_employees",
    "size_preceding_turnover",
    "size_preceding_balance_sheet",
    "size_preceding_employees",
)


def test_migration_adds_the_columns_without_a_read_or_grant_all() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "q3r4s5t6u7"' in source
    assert 'down_revision: Union[str, None] = "m9n0o1p2q3"' in source
    assert "ADD COLUMN size_current_turnover NUMERIC(19, 2)" in source
    assert "ADD COLUMN size_current_balance_sheet NUMERIC(19, 2)" in source
    assert "ADD COLUMN size_current_employees INTEGER" in source
    assert "ADD COLUMN size_preceding_turnover NUMERIC(19, 2)" in source
    assert "ADD COLUMN size_preceding_balance_sheet NUMERIC(19, 2)" in source
    assert "ADD COLUMN size_preceding_employees INTEGER" in source
    assert "size_current_employees >= 0" in source
    assert "size_preceding_employees >= 0" in source
    assert "DROP COLUMN IF EXISTS size_current_turnover" in source
    assert "findraft_table_privileges.sql" in source
    assert "GRANT ALL" not in executable
    assert "SET DEFAULT" not in source
    assert "SELECT" not in executable
    model = _MODEL.read_text()
    service = _SIZE.read_text()
    for name in _COLUMNS:
        assert name in model
        assert name in service
    assert "current_met >= 2" in service
    assert "size_eligibility_recorded" in service
    assert "Turnover and balance-sheet amounts stay off the log" in service
    assert '"rule": "2-of-3"' in _PACK.read_text()


def test_code_head_is_the_size_inputs_revision() -> None:
    assert code_heads() == ("q3r4s5t6u7",)


def test_columns_are_nullable_with_no_server_default() -> None:
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT column_name, is_nullable, column_default, data_type,
                       numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'findraft_year_ends'
                  AND column_name IN (
                    'size_current_turnover',
                    'size_current_balance_sheet',
                    'size_current_employees',
                    'size_preceding_turnover',
                    'size_preceding_balance_sheet',
                    'size_preceding_employees'
                  )
                """
            )
        ).all()
        checks = session.execute(
            text(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conname IN (
                  'findraft_year_ends_size_current_employees_check',
                  'findraft_year_ends_size_preceding_employees_check'
                )
                """
            )
        ).all()
    found = {row.column_name: row for row in rows}
    assert set(found) == set(_COLUMNS)
    for name in (
        "size_current_turnover",
        "size_current_balance_sheet",
        "size_preceding_turnover",
        "size_preceding_balance_sheet",
    ):
        row = found[name]
        assert row.is_nullable == "YES"
        assert row.column_default is None
        assert row.data_type == "numeric"
        assert row.numeric_precision == 19
        assert row.numeric_scale == 2
    for name in ("size_current_employees", "size_preceding_employees"):
        row = found[name]
        assert row.is_nullable == "YES"
        assert row.column_default is None
        assert row.data_type == "integer"
    assert {row.conname for row in checks} == {
        "findraft_year_ends_size_current_employees_check",
        "findraft_year_ends_size_preceding_employees_check",
    }
