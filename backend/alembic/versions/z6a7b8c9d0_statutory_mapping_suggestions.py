"""Store statutory mapping suggestions on parsed trial-balance lines.

Revision ID: z6a7b8c9d0
Revises: y5z6a7b8c9
Create Date: 2026-10-02

Suggestions are written when a statutory trial balance is parsed. They come
from suggest_statutory_mapping. Confidence is the engine score on the 0–1
scale the mapping screen already shows. Null means the engine had no line.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "z6a7b8c9d0"
down_revision: Union[str, None] = "y5z6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_tb_lines
          ADD COLUMN suggested_canonical_line VARCHAR(64),
          ADD COLUMN suggestion_confidence NUMERIC(5, 2),
          ADD COLUMN suggestion_method VARCHAR(64),
          ADD CONSTRAINT findraft_tb_lines_suggestion_confidence_check
            CHECK (
              suggestion_confidence IS NULL
              OR (
                suggestion_confidence >= 0
                AND suggestion_confidence <= 1
              )
            ),
          ADD CONSTRAINT findraft_tb_lines_suggestion_pair_check
            CHECK (
              (
                suggested_canonical_line IS NULL
                AND suggestion_confidence IS NULL
              )
              OR (
                suggested_canonical_line IS NOT NULL
                AND suggestion_confidence IS NOT NULL
              )
            )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_tb_lines
          DROP CONSTRAINT IF EXISTS findraft_tb_lines_suggestion_pair_check,
          DROP CONSTRAINT IF EXISTS findraft_tb_lines_suggestion_confidence_check,
          DROP COLUMN IF EXISTS suggestion_method,
          DROP COLUMN IF EXISTS suggestion_confidence,
          DROP COLUMN IF EXISTS suggested_canonical_line
        """
    )
