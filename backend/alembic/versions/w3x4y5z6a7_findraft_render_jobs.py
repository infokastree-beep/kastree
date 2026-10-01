"""Product 2 Week 11: DOCX render jobs.

Revision ID: w3x4y5z6a7
Revises: v2w3x4y5z6
Create Date: 2026-10-01

The auditor's-report slot is not a table. Note overrides and text blocks
are not created. This table queues a DOCX render only.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "w3x4y5z6a7"
down_revision: Union[str, None] = "v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_POLICY = """
          USING (
            org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          )
          WITH CHECK (
            org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          )
"""


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE findraft_render_jobs (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL REFERENCES organisations (id) ON DELETE CASCADE,
          company_id UUID NOT NULL,
          tb_version_id UUID NOT NULL,
          format VARCHAR(8) NOT NULL DEFAULT 'docx',
          status VARCHAR(16) NOT NULL DEFAULT 'pending',
          idempotency_key VARCHAR(200) NOT NULL,
          storage_key VARCHAR,
          error_message TEXT,
          watermark VARCHAR(16) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT findraft_render_jobs_idempotency_key
            UNIQUE (org_id, idempotency_key),
          CONSTRAINT findraft_render_jobs_id_org_company_key
            UNIQUE (id, org_id, company_id),
          CONSTRAINT findraft_render_jobs_format_check
            CHECK (format = 'docx'),
          CONSTRAINT findraft_render_jobs_status_check
            CHECK (status IN ('pending', 'running', 'ready', 'failed')),
          CONSTRAINT findraft_render_jobs_company_fk
            FOREIGN KEY (org_id, company_id)
            REFERENCES companies (org_id, id) ON DELETE CASCADE,
          CONSTRAINT findraft_render_jobs_version_fk
            FOREIGN KEY (tb_version_id, org_id, company_id)
            REFERENCES findraft_tb_versions (id, org_id, company_id)
            ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_render_jobs_org_id
          ON findraft_render_jobs (org_id)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_render_jobs_tb_version_id
          ON findraft_render_jobs (tb_version_id)
        """
    )
    op.execute("ALTER TABLE findraft_render_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE findraft_render_jobs FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY findraft_render_jobs_org_isolation
          ON findraft_render_jobs
          FOR ALL
          {_POLICY}
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'findraft_app') THEN
            GRANT SELECT, INSERT, UPDATE ON findraft_render_jobs TO findraft_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS findraft_render_jobs")
