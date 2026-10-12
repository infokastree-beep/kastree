"""Nullable legal form on a company. Existing rows stay NULL.

Revision ID: t6u7v8w9x0
Revises: s5t6u7v8w9
Create Date: 2026-10-12

Adds companies.legal_form. There is no server default and no value
constraint. Existing rows stay NULL. The trading or holding type is a
different column and is left alone. This revision does not map the
column, does not read it, and does not write it. Downgrade drops the
column and reapplies least privilege. It does not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "t6u7v8w9x0"
down_revision: Union[str, None] = "s5t6u7v8w9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE companies
          ADD COLUMN legal_form VARCHAR(64)
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE companies
          DROP COLUMN IF EXISTS legal_form
        """
    )
    op.execute(_PRIVILEGES.read_text())
