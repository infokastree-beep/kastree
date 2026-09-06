"""Add copilot_turns audit table and processing_jobs token usage columns.

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-09-06

Append-only copilot_turns mirrors commentary_feedback's org-scoped RLS pattern
(join via trial_balances → companies → clients). Token usage columns on
processing_jobs support Copilot (and future) LLM spend logging. job_type check
widened to include 'copilot'.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "n4o5p6q7r8s9"
down_revision: Union[str, None] = "m3n4o5p6q7r8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "copilot_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "tb_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trial_balances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(), nullable=False),
        sa.Column("evidence_pack", postgresql.JSONB(), nullable=False),
        sa.Column("raw_answer", postgresql.JSONB(), nullable=True),
        sa.Column("grounded_answer", postgresql.JSONB(), nullable=False),
        sa.Column("model_used", sa.String(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "processing_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("processing_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_copilot_turns_tb_id", "copilot_turns", ["tb_id"])
    op.create_index("idx_copilot_turns_org_id", "copilot_turns", ["org_id"])
    op.create_index("idx_copilot_turns_user_id", "copilot_turns", ["user_id"])
    op.create_index("idx_copilot_turns_created_at", "copilot_turns", ["created_at"])

    op.execute("ALTER TABLE copilot_turns ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE copilot_turns FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY copilot_turns_org_isolation ON copilot_turns
          FOR ALL
          USING (
            org_id = current_setting('app.current_org_id')::UUID
            AND tb_id IN (
              SELECT tb.id FROM trial_balances tb
              JOIN companies co ON tb.company_id = co.id
              JOIN clients c ON co.client_id = c.id
              WHERE c.org_id = current_setting('app.current_org_id')::UUID
            )
          )
          WITH CHECK (
            org_id = current_setting('app.current_org_id')::UUID
            AND tb_id IN (
              SELECT tb.id FROM trial_balances tb
              JOIN companies co ON tb.company_id = co.id
              JOIN clients c ON co.client_id = c.id
              WHERE c.org_id = current_setting('app.current_org_id')::UUID
            )
          )
        """
    )

    op.add_column(
        "processing_jobs",
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("total_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("model_used", sa.String(), nullable=True),
    )

    op.drop_constraint("processing_jobs_job_type_check", "processing_jobs", type_="check")
    op.create_check_constraint(
        "processing_jobs_job_type_check",
        "processing_jobs",
        "job_type IN ('parse', 'map', 'validate', 'statements', 'variance', 'risk', 'export', 'copilot')",
    )


def downgrade() -> None:
    op.drop_constraint("processing_jobs_job_type_check", "processing_jobs", type_="check")
    op.create_check_constraint(
        "processing_jobs_job_type_check",
        "processing_jobs",
        "job_type IN ('parse', 'map', 'validate', 'statements', 'variance', 'risk', 'export')",
    )
    op.drop_column("processing_jobs", "model_used")
    op.drop_column("processing_jobs", "total_tokens")
    op.drop_column("processing_jobs", "completion_tokens")
    op.drop_column("processing_jobs", "prompt_tokens")

    op.execute("DROP POLICY IF EXISTS copilot_turns_org_isolation ON copilot_turns")
    op.drop_index("idx_copilot_turns_created_at", table_name="copilot_turns")
    op.drop_index("idx_copilot_turns_user_id", table_name="copilot_turns")
    op.drop_index("idx_copilot_turns_org_id", table_name="copilot_turns")
    op.drop_index("idx_copilot_turns_tb_id", table_name="copilot_turns")
    op.drop_table("copilot_turns")
