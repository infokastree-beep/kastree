"""Remap Accum. abbreviations and doubtful-debt provisions to BS leaves.

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-09-10

Follow-up to m3n4o5p6q7r8:

1. ``Accum. Depreciation`` / ``Accum Depreciation`` abbreviations were missed by
   the earlier ``%accumul%depreci%`` ILIKE (no ``accumul`` stem), so some rows
   still sit on P&L ``depreciation``.
2. Allowance / Provision for Doubtful or Bad Debts must net on
   ``trade_receivables`` — same contra-asset name pattern as Accum → PPE —
   not ``provisions`` / ``unmapped`` / P&L leaves.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "o5p6q7r8s9t0"
down_revision: Union[str, None] = "n4o5p6q7r8s9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Abbreviated Accum. / Accum / Acc. / A/Depn → PPE (never P&L depreciation).
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'property_plant_equipment',
            updated_at = NOW()
        WHERE canonical_line IN ('depreciation', 'amortisation', 'unmapped')
          AND (
            source_name ~* '\\yaccum\\.?\\s*dep(n|reciation)?\\y'
            OR source_name ~* '\\yacc\\.?\\s*dep(n|reciation)?\\y'
            OR source_name ~* '\\ya\\s*/\\s*dep(n|reciation)?\\y'
            OR source_name ILIKE '%accum.%depreci%'
            OR source_name ILIKE '%accum depreci%'
            OR source_name ILIKE '%acc. depreci%'
            OR source_name ILIKE '%a/depn%'
            OR source_name ILIKE '%a/depreciation%'
          )
        """
    )
    # Allowance / provision for doubtful or bad debts → trade_receivables.
    # Exclude P&L expense / write-off wording.
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'trade_receivables',
            updated_at = NOW()
        WHERE canonical_line IS DISTINCT FROM 'trade_receivables'
          AND source_name !~* '\\y(expense|written off|write[- ]?offs?|charge)\\y'
          AND (
            source_name ILIKE '%allowance for doubtful%'
            OR source_name ILIKE '%allowance for bad debt%'
            OR source_name ILIKE '%allowance for expected credit%'
            OR source_name ILIKE '%provision for doubtful%'
            OR source_name ILIKE '%provision for bad debt%'
            OR source_name ILIKE '%expected credit loss%'
            OR source_name ILIKE '%doubtful debt%'
          )
        """
    )


def downgrade() -> None:
    # Best-effort only — cannot recover prior wrong leaves safely.
    pass
