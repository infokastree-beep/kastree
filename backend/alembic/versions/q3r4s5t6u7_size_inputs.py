"""Nullable size-test inputs on a year end. Existing rows stay NULL.

Revision ID: q3r4s5t6u7
Revises: m9n0o1p2q3
Create Date: 2026-10-12

Adds the turnover, balance-sheet total, and employee count for the current
year and the preceding year. There is no server default. Existing rows stay
NULL. NULL means those figures have not been stored. This revision does not
read or write the columns, does not map them on the model, and does not
change the stored size result. Downgrade drops the columns and reapplies
least privilege. It does not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "q3r4s5t6u7"
down_revision: Union[str, None] = "m9n0o1p2q3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD COLUMN size_current_turnover NUMERIC(19, 2),
          ADD COLUMN size_current_balance_sheet NUMERIC(19, 2),
          ADD COLUMN size_current_employees INTEGER,
          ADD COLUMN size_preceding_turnover NUMERIC(19, 2),
          ADD COLUMN size_preceding_balance_sheet NUMERIC(19, 2),
          ADD COLUMN size_preceding_employees INTEGER,
          ADD CONSTRAINT findraft_year_ends_size_current_employees_check
            CHECK (
              size_current_employees IS NULL OR size_current_employees >= 0
            ),
          ADD CONSTRAINT findraft_year_ends_size_preceding_employees_check
            CHECK (
              size_preceding_employees IS NULL
              OR size_preceding_employees >= 0
            )
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP CONSTRAINT IF EXISTS findraft_year_ends_size_current_employees_check,
          DROP CONSTRAINT IF EXISTS findraft_year_ends_size_preceding_employees_check,
          DROP COLUMN IF EXISTS size_current_turnover,
          DROP COLUMN IF EXISTS size_current_balance_sheet,
          DROP COLUMN IF EXISTS size_current_employees,
          DROP COLUMN IF EXISTS size_preceding_turnover,
          DROP COLUMN IF EXISTS size_preceding_balance_sheet,
          DROP COLUMN IF EXISTS size_preceding_employees
        """
    )
    op.execute(_PRIVILEGES.read_text())
