"""Product 2 Week 3: immutable TB versions and prior-year gate data.

Revision ID: s9t0u1v2w3
Revises: r8s9t0u1v2w
Create Date: 2026-09-30

Trial-balance versions are immutable once parsed. A draft records the version
it was built from. Prior-year canonical balances lock when validated.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "s9t0u1v2w3"
down_revision: Union[str, None] = "r8s9t0u1v2w"
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
        ALTER TABLE findraft_year_ends
          ADD COLUMN first_financial_period BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD CONSTRAINT findraft_year_ends_id_org_company_key
          UNIQUE (id, org_id, company_id)
        """
    )
    op.execute(
        """
        ALTER TABLE findraft_source_documents
          ADD CONSTRAINT findraft_source_documents_id_org_company_key
          UNIQUE (id, org_id, company_id)
        """
    )
    op.execute(
        """
        CREATE TABLE findraft_tb_versions (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL REFERENCES organisations (id) ON DELETE CASCADE,
          company_id UUID NOT NULL,
          year_end_id UUID NOT NULL,
          version_number INTEGER NOT NULL,
          source_document_id UUID NOT NULL,
          status VARCHAR(16) NOT NULL DEFAULT 'pending',
          error_message TEXT,
          idempotency_key VARCHAR(200) NOT NULL,
          created_by_user_id UUID REFERENCES users (id) ON DELETE SET NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT findraft_tb_versions_number_key
            UNIQUE (year_end_id, version_number),
          CONSTRAINT findraft_tb_versions_idempotency_key
            UNIQUE (org_id, idempotency_key),
          CONSTRAINT findraft_tb_versions_number_check
            CHECK (version_number >= 1),
          CONSTRAINT findraft_tb_versions_status_check
            CHECK (status IN ('pending', 'ready', 'failed')),
          CONSTRAINT findraft_tb_versions_company_fk
            FOREIGN KEY (org_id, company_id)
            REFERENCES companies (org_id, id) ON DELETE CASCADE,
          CONSTRAINT findraft_tb_versions_year_end_fk
            FOREIGN KEY (year_end_id, org_id, company_id)
            REFERENCES findraft_year_ends (id, org_id, company_id) ON DELETE CASCADE,
          CONSTRAINT findraft_tb_versions_source_fk
            FOREIGN KEY (source_document_id, org_id, company_id)
            REFERENCES findraft_source_documents (id, org_id, company_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_findraft_tb_versions_org_id ON findraft_tb_versions (org_id)"
    )
    op.execute(
        """
        CREATE TABLE findraft_tb_lines (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL REFERENCES organisations (id) ON DELETE CASCADE,
          company_id UUID NOT NULL,
          tb_version_id UUID NOT NULL REFERENCES findraft_tb_versions (id) ON DELETE CASCADE,
          line_no INTEGER NOT NULL,
          nominal_code VARCHAR(64) NOT NULL,
          account_name VARCHAR(500) NOT NULL,
          debit NUMERIC(15, 2) NOT NULL,
          credit NUMERIC(15, 2) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT findraft_tb_lines_number_key UNIQUE (tb_version_id, line_no),
          CONSTRAINT findraft_tb_lines_line_check CHECK (line_no >= 1),
          CONSTRAINT findraft_tb_lines_debit_check CHECK (debit >= 0),
          CONSTRAINT findraft_tb_lines_credit_check CHECK (credit >= 0),
          CONSTRAINT findraft_tb_lines_company_fk
            FOREIGN KEY (org_id, company_id)
            REFERENCES companies (org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_findraft_tb_lines_org_id ON findraft_tb_lines (org_id)"
    )
    op.execute(
        """
        CREATE TABLE findraft_prior_year_lines (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL REFERENCES organisations (id) ON DELETE CASCADE,
          company_id UUID NOT NULL,
          year_end_id UUID NOT NULL,
          canonical_line VARCHAR(64) NOT NULL,
          amount NUMERIC(15, 2) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT findraft_prior_year_lines_line_key
            UNIQUE (year_end_id, canonical_line),
          CONSTRAINT findraft_prior_year_lines_company_fk
            FOREIGN KEY (org_id, company_id)
            REFERENCES companies (org_id, id) ON DELETE CASCADE,
          CONSTRAINT findraft_prior_year_lines_year_end_fk
            FOREIGN KEY (year_end_id, org_id, company_id)
            REFERENCES findraft_year_ends (id, org_id, company_id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_prior_year_lines_org_id
          ON findraft_prior_year_lines (org_id)
        """
    )
    op.execute(
        """
        ALTER TABLE findraft_draft_versions
          ADD COLUMN tb_version_id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE findraft_draft_versions
          ADD CONSTRAINT findraft_draft_versions_tb_fk
          FOREIGN KEY (tb_version_id) REFERENCES findraft_tb_versions (id)
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_tb_versions_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF OLD.status <> 'pending' THEN
            RAISE EXCEPTION 'trial balance version is immutable';
          END IF;
          IF NEW.org_id IS DISTINCT FROM OLD.org_id
             OR NEW.company_id IS DISTINCT FROM OLD.company_id
             OR NEW.year_end_id IS DISTINCT FROM OLD.year_end_id
             OR NEW.version_number IS DISTINCT FROM OLD.version_number
             OR NEW.source_document_id IS DISTINCT FROM OLD.source_document_id
             OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key THEN
            RAISE EXCEPTION 'trial balance version identity is immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_tb_versions_immutable
        BEFORE UPDATE ON findraft_tb_versions
        FOR EACH ROW
        EXECUTE FUNCTION findraft_tb_versions_immutable();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_tb_lines_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'trial balance lines are immutable';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_tb_lines_immutable
        BEFORE UPDATE ON findraft_tb_lines
        FOR EACH ROW
        EXECUTE FUNCTION findraft_tb_lines_immutable();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_prior_year_lines_locked()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          locked boolean;
          year_end uuid;
        BEGIN
          year_end := COALESCE(NEW.year_end_id, OLD.year_end_id);
          SELECT prior_year_validated INTO locked
            FROM findraft_year_ends WHERE id = year_end;
          IF locked THEN
            RAISE EXCEPTION 'prior year is already validated';
          END IF;
          RETURN COALESCE(NEW, OLD);
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_prior_year_lines_locked
        BEFORE INSERT OR UPDATE OR DELETE ON findraft_prior_year_lines
        FOR EACH ROW
        EXECUTE FUNCTION findraft_prior_year_lines_locked();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_year_ends_prior_locked()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF OLD.prior_year_validated THEN
            RAISE EXCEPTION 'prior year is already validated';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_year_ends_prior_locked
        BEFORE UPDATE OF prior_year_validated, first_financial_period
        ON findraft_year_ends
        FOR EACH ROW
        EXECUTE FUNCTION findraft_year_ends_prior_locked();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_draft_versions_tb_locked()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF OLD.tb_version_id IS NOT NULL
             AND NEW.tb_version_id IS DISTINCT FROM OLD.tb_version_id THEN
            RAISE EXCEPTION
              'draft already records a trial balance version — create a new draft version';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_draft_versions_tb_locked
        BEFORE UPDATE OF tb_version_id ON findraft_draft_versions
        FOR EACH ROW
        EXECUTE FUNCTION findraft_draft_versions_tb_locked();
        """
    )
    for table in (
        "findraft_tb_versions",
        "findraft_tb_lines",
        "findraft_prior_year_lines",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_org_isolation ON {table}
              FOR ALL
              {_POLICY}
            """
        )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'findraft_app') THEN
            GRANT SELECT, INSERT, UPDATE ON findraft_tb_versions TO findraft_app;
            GRANT SELECT, INSERT ON findraft_tb_lines TO findraft_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON findraft_prior_year_lines TO findraft_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS findraft_draft_versions_tb_locked ON findraft_draft_versions"
    )
    op.execute("DROP FUNCTION IF EXISTS findraft_draft_versions_tb_locked()")
    op.execute(
        "ALTER TABLE findraft_draft_versions DROP CONSTRAINT IF EXISTS findraft_draft_versions_tb_fk"
    )
    op.execute(
        "ALTER TABLE findraft_draft_versions DROP COLUMN IF EXISTS tb_version_id"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS findraft_year_ends_prior_locked ON findraft_year_ends"
    )
    op.execute("DROP FUNCTION IF EXISTS findraft_year_ends_prior_locked()")
    op.execute("DROP TABLE IF EXISTS findraft_prior_year_lines")
    op.execute("DROP FUNCTION IF EXISTS findraft_prior_year_lines_locked()")
    op.execute("DROP TABLE IF EXISTS findraft_tb_lines")
    op.execute("DROP FUNCTION IF EXISTS findraft_tb_lines_immutable()")
    op.execute("DROP TABLE IF EXISTS findraft_tb_versions")
    op.execute("DROP FUNCTION IF EXISTS findraft_tb_versions_immutable()")
    op.execute(
        """
        ALTER TABLE findraft_source_documents
          DROP CONSTRAINT IF EXISTS findraft_source_documents_id_org_company_key
        """
    )
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP CONSTRAINT IF EXISTS findraft_year_ends_id_org_company_key
        """
    )
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP COLUMN IF EXISTS first_financial_period
        """
    )
