"""One SOPL, SOFP, and SOCIE row per trial balance.

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-09-30

Concurrent statement replaces could insert a second copy of the same
statement type. Keep the newest row for each (tb_id, statement_type) and
then forbid duplicates. statement_line_items cascade with the deleted parent.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, None] = "o5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM financial_statements
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY tb_id, statement_type
                           ORDER BY generated_at DESC, created_at DESC, id DESC
                       ) AS rn
                FROM financial_statements
            ) ranked
            WHERE rn > 1
        )
        """
    )
    op.create_unique_constraint(
        "financial_statements_tb_id_statement_type_key",
        "financial_statements",
        ["tb_id", "statement_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "financial_statements_tb_id_statement_type_key",
        "financial_statements",
        type_="unique",
    )
