"""Least privilege for the findraft login.

Revision ID: e1f2a3b4c5
Revises: d0e1f2a3b4
Create Date: 2026-10-08

Revokes TRUNCATE, REFERENCES, and TRIGGER on every public table, and
revokes UPDATE and DELETE on append-only and fully immutable tables.
Sequences are unchanged. The same statement lives in
backend/scripts/findraft_table_privileges.sql so the provision script
cannot grant those privileges back.

Apply this after d0e1f2a3b4. It is the only revision after that one.
Do not run it against production until the smoke checklist in
docs/findraft-least-privilege.md has a reader.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "e1f2a3b4c5"
down_revision: Union[str, None] = "d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO findraft")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO findraft"
    )
