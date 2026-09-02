"""Remap amortisation-named P&L accounts from depreciation to amortisation.

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-09-02

Option A consistency: amortisation is a separate canonical line from
depreciation. Production has P&L expense rows (e.g. Amortisation - Software /
Goodwill) previously mapped to depreciation via 7000–7999 code_range or manual
confirm. Remap those by source_name. Leave Accumulated Amortisation balance-
sheet contra accounts alone (they are not canonical_line = depreciation).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'amortisation'
        WHERE canonical_line = 'depreciation'
          AND source_name ILIKE '%amort%'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'depreciation'
        WHERE canonical_line = 'amortisation'
        """
    )
