"""Product 2 Week 4: fixed-asset versions and the small-company size check.

Revision ID: t0u1v2w3x4
Revises: s9t0u1v2w3
Create Date: 2026-09-30

Fixed-asset classes are immutable once parsed. The journal parser stays cut.
Size eligibility is stored on the year end and can be re-checked.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "t0u1v2w3x4"
down_revision: Union[str, None] = "s9t0u1v2w3"
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
          ADD COLUMN size_eligible BOOLEAN,
          ADD COLUMN size_message TEXT,
          ADD COLUMN size_current_met INTEGER,
          ADD COLUMN size_preceding_met INTEGER,
          ADD COLUMN size_checked_at TIMESTAMPTZ,
          ADD CONSTRAINT findraft_year_ends_size_current_check
            CHECK (size_current_met IS NULL OR size_current_met BETWEEN 0 AND 3),
          ADD CONSTRAINT findraft_year_ends_size_preceding_check
            CHECK (size_preceding_met IS NULL OR size_preceding_met BETWEEN 0 AND 3)
        """
    )
    op.execute(
        """
        CREATE TABLE findraft_fa_versions (
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
          CONSTRAINT findraft_fa_versions_number_key
            UNIQUE (year_end_id, version_number),
          CONSTRAINT findraft_fa_versions_idempotency_key
            UNIQUE (org_id, idempotency_key),
          CONSTRAINT findraft_fa_versions_number_check
            CHECK (version_number >= 1),
          CONSTRAINT findraft_fa_versions_status_check
            CHECK (status IN ('pending', 'ready', 'failed')),
          CONSTRAINT findraft_fa_versions_company_fk
            FOREIGN KEY (org_id, company_id)
            REFERENCES companies (org_id, id) ON DELETE CASCADE,
          CONSTRAINT findraft_fa_versions_year_end_fk
            FOREIGN KEY (year_end_id, org_id, company_id)
            REFERENCES findraft_year_ends (id, org_id, company_id) ON DELETE CASCADE,
          CONSTRAINT findraft_fa_versions_source_fk
            FOREIGN KEY (source_document_id, org_id, company_id)
            REFERENCES findraft_source_documents (id, org_id, company_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_findraft_fa_versions_org_id ON findraft_fa_versions (org_id)"
    )
    op.execute(
        """
        CREATE TABLE findraft_fa_lines (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL REFERENCES organisations (id) ON DELETE CASCADE,
          company_id UUID NOT NULL,
          fa_version_id UUID NOT NULL
            REFERENCES findraft_fa_versions (id) ON DELETE CASCADE,
          line_no INTEGER NOT NULL,
          asset_class VARCHAR(200) NOT NULL,
          opening_cost NUMERIC(15, 2) NOT NULL,
          additions NUMERIC(15, 2) NOT NULL,
          disposals NUMERIC(15, 2) NOT NULL,
          disposals_dep NUMERIC(15, 2) NOT NULL,
          opening_dep NUMERIC(15, 2) NOT NULL,
          charge NUMERIC(15, 2) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT findraft_fa_lines_number_key UNIQUE (fa_version_id, line_no),
          CONSTRAINT findraft_fa_lines_class_key UNIQUE (fa_version_id, asset_class),
          CONSTRAINT findraft_fa_lines_line_check CHECK (line_no >= 1),
          CONSTRAINT findraft_fa_lines_opening_cost_check CHECK (opening_cost >= 0),
          CONSTRAINT findraft_fa_lines_additions_check CHECK (additions >= 0),
          CONSTRAINT findraft_fa_lines_disposals_check CHECK (disposals >= 0),
          CONSTRAINT findraft_fa_lines_disposals_dep_check CHECK (disposals_dep >= 0),
          CONSTRAINT findraft_fa_lines_opening_dep_check CHECK (opening_dep >= 0),
          CONSTRAINT findraft_fa_lines_charge_check CHECK (charge >= 0),
          CONSTRAINT findraft_fa_lines_company_fk
            FOREIGN KEY (org_id, company_id)
            REFERENCES companies (org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_findraft_fa_lines_org_id ON findraft_fa_lines (org_id)"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_fa_versions_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF OLD.status <> 'pending' THEN
            RAISE EXCEPTION 'fixed asset version is immutable';
          END IF;
          IF NEW.org_id IS DISTINCT FROM OLD.org_id
             OR NEW.company_id IS DISTINCT FROM OLD.company_id
             OR NEW.year_end_id IS DISTINCT FROM OLD.year_end_id
             OR NEW.version_number IS DISTINCT FROM OLD.version_number
             OR NEW.source_document_id IS DISTINCT FROM OLD.source_document_id
             OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key THEN
            RAISE EXCEPTION 'fixed asset version identity is immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_fa_versions_immutable
        BEFORE UPDATE ON findraft_fa_versions
        FOR EACH ROW
        EXECUTE FUNCTION findraft_fa_versions_immutable();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_fa_lines_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'fixed asset lines are immutable';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_fa_lines_immutable
        BEFORE UPDATE ON findraft_fa_lines
        FOR EACH ROW
        EXECUTE FUNCTION findraft_fa_lines_immutable();
        """
    )
    for table in ("findraft_fa_versions", "findraft_fa_lines"):
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
            GRANT SELECT, INSERT, UPDATE ON findraft_fa_versions TO findraft_app;
            GRANT SELECT, INSERT ON findraft_fa_lines TO findraft_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS findraft_fa_lines_immutable ON findraft_fa_lines")
    op.execute("DROP TABLE IF EXISTS findraft_fa_lines")
    op.execute("DROP FUNCTION IF EXISTS findraft_fa_lines_immutable()")
    op.execute(
        "DROP TRIGGER IF EXISTS findraft_fa_versions_immutable ON findraft_fa_versions"
    )
    op.execute("DROP TABLE IF EXISTS findraft_fa_versions")
    op.execute("DROP FUNCTION IF EXISTS findraft_fa_versions_immutable()")
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP CONSTRAINT IF EXISTS findraft_year_ends_size_preceding_check,
          DROP CONSTRAINT IF EXISTS findraft_year_ends_size_current_check,
          DROP COLUMN IF EXISTS size_checked_at,
          DROP COLUMN IF EXISTS size_preceding_met,
          DROP COLUMN IF EXISTS size_current_met,
          DROP COLUMN IF EXISTS size_message,
          DROP COLUMN IF EXISTS size_eligible
        """
    )
