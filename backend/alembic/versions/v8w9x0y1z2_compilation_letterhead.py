"""Nullable practice letterhead on the organisation. Existing rows stay NULL.

Revision ID: v8w9x0y1z2
Revises: u7v8w9x0y1
Create Date: 2026-10-13

The compilation report already prints organisations.name. No written column
list names anything further. These two fields are the address and the
contact line a compilation letterhead still has to show. There is no server
default and no value constraint. Existing rows stay NULL. This revision
does not map the columns, does not read them, and does not write them.
Downgrade drops the columns and reapplies least privilege. It does not
GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "v8w9x0y1z2"
down_revision: Union[str, None] = "u7v8w9x0y1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE organisations
          ADD COLUMN letterhead_address TEXT,
          ADD COLUMN letterhead_contact TEXT
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE organisations
          DROP COLUMN IF EXISTS letterhead_address,
          DROP COLUMN IF EXISTS letterhead_contact
        """
    )
    op.execute(_PRIVILEGES.read_text())
