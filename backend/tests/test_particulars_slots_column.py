"""Revision x0y1z2a3b4 adds particulars slots. The model maps them."""

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
    / "x0y1z2a3b4_particulars_slots.py"
)
_MODEL = Path(__file__).resolve().parents[2] / "findraft" / "models" / "year_end.py"
_COLUMNS = (
    "related_party_particulars",
    "directors_remuneration_particulars",
    "loan_terms_particulars",
    "guarantee_particulars",
)


def test_migration_adds_the_slots_without_a_read_or_grant_all() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "x0y1z2a3b4"' in source
    assert 'down_revision: Union[str, None] = "w9x0y1z2a3"' in source
    model = _MODEL.read_text()
    for name in _COLUMNS:
        assert f"ADD COLUMN {name} TEXT" in source
        assert f"DROP COLUMN IF EXISTS {name}" in source
        assert name in YearEnd.__table__.columns
        assert (
            f"{name}: Mapped[str | None] = mapped_column(\n        Text, nullable=True, default=None\n    )"
            in model
        )
    assert "subsequent_events_particulars" not in executable
    assert "share_classes" not in executable
    assert "findraft_table_privileges.sql" in source
    assert "GRANT ALL" not in executable
    assert "SET DEFAULT" not in source
    assert "CHECK" not in source
    assert "SELECT" not in executable


def test_code_head_is_the_particulars_slots_revision() -> None:
    assert code_heads() == ("o1p2q3r4s5",)


def test_columns_are_nullable_text_with_no_server_default() -> None:
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT column_name, is_nullable, column_default, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'findraft_year_ends'
                  AND column_name IN (
                    'related_party_particulars',
                    'directors_remuneration_particulars',
                    'loan_terms_particulars',
                    'guarantee_particulars'
                  )
                """
            )
        ).all()
    found = {row.column_name: row for row in rows}
    assert set(found) == set(_COLUMNS)
    for row in found.values():
        assert row.is_nullable == "YES"
        assert row.column_default is None
        assert row.data_type == "text"
