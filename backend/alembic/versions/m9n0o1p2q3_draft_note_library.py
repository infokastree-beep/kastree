"""Nullable note library on a draft. Existing drafts stay NULL.

Revision ID: m9n0o1p2q3
Revises: l8m9n0o1p2
Create Date: 2026-10-11

Adds findraft_draft_versions.note_library. There is no server default.
Existing rows stay NULL. NULL means the preparer has neither omitted nor
added a block. This revision does not select the column, does not map it
on the model, and does not alter companies. Downgrade drops the column and
reapplies least privilege. It does not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "m9n0o1p2q3"
down_revision: Union[str, None] = "l8m9n0o1p2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_draft_versions
          ADD COLUMN note_library JSONB
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_draft_versions
          DROP COLUMN IF EXISTS note_library
        """
    )
    op.execute(_PRIVILEGES.read_text())
