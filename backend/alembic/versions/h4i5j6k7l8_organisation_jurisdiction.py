"""Nullable practice jurisdiction. No company updates.

Revision ID: h4i5j6k7l8
Revises: g3h4i5j6k7
Create Date: 2026-10-09

Adds organisations.jurisdiction. Existing organisations stay NULL, and no
company row is updated. Ireland (IE) is read by company create to preselect
EUR. Downgrade drops the column and reapplies least privilege. It does not
GRANT ALL.

Revision order: f2a3b4c5d6 -> g3h4i5j6k7 (#79) -> h4i5j6k7l8 (this).
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "h4i5j6k7l8"
down_revision: Union[str, None] = "g3h4i5j6k7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE organisations
          ADD COLUMN jurisdiction VARCHAR(2)
        """
    )
    op.execute(
        """
        ALTER TABLE organisations
          ADD CONSTRAINT organisations_jurisdiction_check
          CHECK (jurisdiction IS NULL OR jurisdiction IN ('IE', 'GB'))
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE organisations
          DROP CONSTRAINT IF EXISTS organisations_jurisdiction_check,
          DROP COLUMN IF EXISTS jurisdiction
        """
    )
    op.execute(_PRIVILEGES.read_text())
