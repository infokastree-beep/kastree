"""Revision n0o1p2q3r4 adds trial_balances.original_filename. The model maps it."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db import SyncSessionLocal
from app.models.trial_balance import TrialBalance
from app.services.schema_revision import code_heads

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "n0o1p2q3r4_trial_balance_original_filename.py"
)
_MODEL = Path(__file__).resolve().parents[1] / "app" / "models" / "trial_balance.py"


def test_migration_adds_the_column_without_a_read_or_grant_all() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "n0o1p2q3r4"' in source
    assert 'down_revision: Union[str, None] = "z2a3b4c5d6"' in source
    assert "ADD COLUMN original_filename VARCHAR(255)" in source
    assert "DROP COLUMN IF EXISTS original_filename" in source
    assert "CHECK" not in source
    assert "findraft_table_privileges.sql" in source
    assert "GRANT ALL" not in executable
    assert "SET DEFAULT" not in source
    assert "SELECT" not in executable
    model = _MODEL.read_text()
    column = model.split("original_filename:", 1)[1].split("raw_data:", 1)[0]
    assert "original_filename" in TrialBalance.__table__.columns
    assert "Mapped[str | None]" in column
    assert "String(255)" in column
    assert "nullable=True" in column
    assert "server_default" not in column


def test_code_head_is_the_original_filename_revision() -> None:
    assert code_heads() == ("o1p2q3r4s5",)


def test_column_is_nullable_with_no_server_default() -> None:
    with SyncSessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT is_nullable, column_default, data_type, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'trial_balances'
                  AND column_name = 'original_filename'
                """
            )
        ).one()
    assert row.is_nullable == "YES"
    assert row.column_default is None
    assert row.data_type == "character varying"
    assert row.character_maximum_length == 255
