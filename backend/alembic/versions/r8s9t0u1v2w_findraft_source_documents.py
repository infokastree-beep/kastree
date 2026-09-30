"""Product 2 Week 2: per-practice source documents.

Revision ID: r8s9t0u1v2w
Revises: q7r8s9t0u1v2
Create Date: 2026-09-30

Stores an uploaded file for one organisation and company. Tenant isolation
uses app.current_org_id. The verified file type is pdf, xlsx, or csv.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "r8s9t0u1v2w"
down_revision: Union[str, None] = "q7r8s9t0u1v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE findraft_source_documents (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL REFERENCES organisations (id) ON DELETE CASCADE,
          company_id UUID NOT NULL,
          storage_key VARCHAR NOT NULL,
          original_filename VARCHAR(255) NOT NULL,
          detected_type VARCHAR(8) NOT NULL,
          byte_size BIGINT NOT NULL,
          sha256 VARCHAR(64) NOT NULL,
          idempotency_key VARCHAR(200) NOT NULL,
          created_by_user_id UUID REFERENCES users (id) ON DELETE SET NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT findraft_source_documents_idempotency_key
            UNIQUE (org_id, idempotency_key),
          CONSTRAINT findraft_source_documents_company_fk
            FOREIGN KEY (org_id, company_id)
            REFERENCES companies (org_id, id) ON DELETE CASCADE,
          CONSTRAINT findraft_source_documents_type_check
            CHECK (detected_type IN ('pdf', 'xlsx', 'csv')),
          CONSTRAINT findraft_source_documents_size_check
            CHECK (byte_size > 0 AND byte_size <= 52428800)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_source_documents_org_id
          ON findraft_source_documents (org_id)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_source_documents_company_id
          ON findraft_source_documents (company_id)
        """
    )
    # SET ROLE findraft_app reports an unset custom GUC as '' rather than NULL.
    op.execute("ALTER TABLE findraft_source_documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE findraft_source_documents FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY findraft_source_documents_org_isolation
          ON findraft_source_documents
          FOR ALL
          USING (
            org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          )
          WITH CHECK (
            org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          )
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'findraft_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON findraft_source_documents TO findraft_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS findraft_source_documents")
