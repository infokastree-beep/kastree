"""Nullable compilation date and signatory on the year end. Existing rows stay NULL.

Revision ID: w9x0y1z2a3
Revises: v8w9x0y1z2
Create Date: 2026-10-13

The compilation report is the practice's report. approval_date and
signing_directors stay the directors' approval of the financial statements.
These two columns are the date of the compilation report and the person who
signs it. There is no server default and no value constraint. Existing rows
stay NULL. This revision does not map the columns, does not read them, and
does not write them. Downgrade drops the columns and reapplies least
privilege. It does not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "w9x0y1z2a3"
down_revision: Union[str, None] = "v8w9x0y1z2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD COLUMN compilation_date DATE,
          ADD COLUMN compilation_signatory TEXT
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP COLUMN IF EXISTS compilation_date,
          DROP COLUMN IF EXISTS compilation_signatory
        """
    )
    op.execute(_PRIVILEGES.read_text())
