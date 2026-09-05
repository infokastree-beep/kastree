"""Remap Accumulated Depreciation/Amortisation from P&L lines to BS assets.

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-09-05

Accumulated Depreciation accounts were incorrectly mapped to canonical_line =
depreciation (P&L). Their credit balances then (a) never netted against SOFP
property_plant_equipment and (b) polluted SOPL Depreciation (often flipping it
negative). Same pattern for Accumulated Amortisation vs amortisation /
intangible_assets.

Fix: map BS contra-assets onto the related debit-normal asset leaf so existing
``_statement_amount`` netting produces cost − accumulated on the SOFP, and P&L
charge lines stay period expense only.

Also re-apply the amortisation-named P&L charge remap (depreciation →
amortisation) idempotently for rows that still sit on depreciation.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, None] = "l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Accumulated / provision-for depreciation → PPE (SOFP contra-asset).
    # Include unmapped rows so contras are not left off the SOFP netting leaf.
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'property_plant_equipment',
            updated_at = NOW()
        WHERE canonical_line IN ('depreciation', 'amortisation', 'unmapped')
          AND (
            source_name ILIKE '%accumul%depreci%'
            OR source_name ILIKE '%depreci%accumul%'
            OR source_name ILIKE '%provision for depreci%'
          )
        """
    )
    # Accumulated / provision-for amortisation → intangibles (SOFP contra-asset).
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'intangible_assets',
            updated_at = NOW()
        WHERE canonical_line IN ('depreciation', 'amortisation', 'unmapped')
          AND (
            source_name ILIKE '%accumul%amort%'
            OR source_name ILIKE '%amort%accumul%'
            OR source_name ILIKE '%provision for amort%'
          )
        """
    )
    # Idempotent re-apply: P&L amortisation charges must not sit on depreciation.
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'amortisation',
            updated_at = NOW()
        WHERE canonical_line = 'depreciation'
          AND source_name ILIKE '%amort%'
          AND source_name NOT ILIKE '%accumul%'
          AND source_name NOT ILIKE '%provision for amort%'
        """
    )


def downgrade() -> None:
    # Best-effort reverse: only rows that look like BS contras on asset leaves.
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'depreciation',
            updated_at = NOW()
        WHERE canonical_line = 'property_plant_equipment'
          AND (
            source_name ILIKE '%accumul%depreci%'
            OR source_name ILIKE '%depreci%accumul%'
            OR source_name ILIKE '%provision for depreci%'
          )
        """
    )
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'amortisation',
            updated_at = NOW()
        WHERE canonical_line = 'intangible_assets'
          AND (
            source_name ILIKE '%accumul%amort%'
            OR source_name ILIKE '%amort%accumul%'
            OR source_name ILIKE '%provision for amort%'
          )
        """
    )
