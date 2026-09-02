"""Revert accruals_and_deferred_income -> accruals; keep deferred_income separate.

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-09-02

Course correction: Option A (regime-neutral granular lines). Combined
accruals_and_deferred_income is split back into accruals + deferred_income.
Production has one row (JIE JIE LTD / 2100 / Accruals) that was renamed to
accruals_and_deferred_income by g7h8i9j0k1l2 — restore it to accruals because
the source account is literally Accruals with no deferred-income component.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'accruals'
        WHERE canonical_line = 'accruals_and_deferred_income'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'accruals_and_deferred_income'
        WHERE canonical_line = 'accruals'
        """
    )
