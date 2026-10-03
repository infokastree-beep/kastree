"""Store draft report-setup display settings on the year end.

Revision ID: c9d0e1f2a3
Revises: b8c9d0e1f2
Create Date: 2026-10-03

Rounding, face dates, statement type, and column headers are presentation.
They are not trial-balance dates and they are not statement figures.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c9d0e1f2a3"
down_revision: Union[str, None] = "b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD COLUMN report_setup JSONB
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP COLUMN IF EXISTS report_setup
        """
    )
