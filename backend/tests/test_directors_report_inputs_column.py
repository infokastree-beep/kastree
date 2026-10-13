"""Revision u7v8w9x0y1 adds directors' report inputs. The model maps them."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db import SyncSessionLocal
from app.services.schema_revision import code_heads

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "u7v8w9x0y1_directors_report_inputs.py"
)
_MODEL = Path(__file__).resolve().parents[2] / "findraft" / "models" / "year_end.py"
_COLUMNS = (
    "accounting_records_location",
    "interim_dividend",
    "recommended_dividend",
    "share_interests",
    "own_shares_particulars",
    "subsequent_events_particulars",
    "research_development_relevant",
    "research_development_detail",
    "political_donations_relevant",
    "political_donations_detail",
    "accounting_period_change_filed",
)


def test_migration_adds_the_columns_without_a_read_or_grant_all() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "u7v8w9x0y1"' in source
    assert 'down_revision: Union[str, None] = "t6u7v8w9x0"' in source
    for name in _COLUMNS:
        assert f"ADD COLUMN {name} " in source or f"ADD COLUMN {name}\n" in source
        assert f"DROP COLUMN IF EXISTS {name}" in source
    assert "NUMERIC(19, 2)" in source
    assert "findraft_table_privileges.sql" in source
    assert "GRANT ALL" not in executable
    assert "SET DEFAULT" not in source
    assert "CHECK" not in source
    assert "SELECT" not in executable
    model = _MODEL.read_text()
    for name in _COLUMNS:
        assert name in model


def test_code_head_is_the_directors_report_inputs_revision() -> None:
    assert code_heads() == ("u7v8w9x0y1",)


def test_columns_are_nullable_with_no_server_default() -> None:
    with SyncSessionLocal() as session:
        names = {f"n{index}": name for index, name in enumerate(_COLUMNS)}
        placeholders = ", ".join(f":n{index}" for index in range(len(_COLUMNS)))
        rows = session.execute(
            text(
                f"""
                SELECT column_name, is_nullable, column_default, data_type,
                       numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'findraft_year_ends'
                  AND column_name IN ({placeholders})
                """
            ),
            names,
        ).all()
    found = {row.column_name: row for row in rows}
    assert set(found) == set(_COLUMNS)
    for row in found.values():
        assert row.is_nullable == "YES"
        assert row.column_default is None
    assert found["interim_dividend"].data_type == "numeric"
    assert found["interim_dividend"].numeric_precision == 19
    assert found["interim_dividend"].numeric_scale == 2
    assert found["recommended_dividend"].numeric_precision == 19
    assert found["recommended_dividend"].numeric_scale == 2
    assert found["share_interests"].data_type == "jsonb"
    assert found["accounting_records_location"].data_type == "text"
    assert found["research_development_relevant"].data_type == "boolean"
    assert found["political_donations_relevant"].data_type == "boolean"
    assert found["accounting_period_change_filed"].data_type == "boolean"
