"""Nullable original file name on a trial balance. Existing rows stay NULL.

Revision ID: n0o1p2q3r4
Revises: z2a3b4c5d6
Create Date: 2026-10-14

Queue item 12. The design named this revision after m9n0o1p2q3. That
parent is no longer the head. The head is z2a3b4c5d6, so this revision
continues that chain and does not fork it.

trial_balances.original_filename VARCHAR(255) NULL. No server default.
No backfill. No check constraint. Existing rows stay null. The switch
itself does not use this column. This revision does not map the column,
does not read it, and does not write it. Upgrade and downgrade reapply
least privilege. It does not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "n0o1p2q3r4"
down_revision: Union[str, None] = "z2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE trial_balances
          ADD COLUMN original_filename VARCHAR(255)
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE trial_balances
          DROP COLUMN IF EXISTS original_filename
        """
    )
    op.execute(_PRIVILEGES.read_text())
