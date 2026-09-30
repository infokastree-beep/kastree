"""Product 2 Phase 1: entity record, pack pin, tenant composite keys.

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-09-30

Extends the existing companies table. Tenant isolation stays on
app.current_org_id. No journal, bank-rec, or evidence-graph tables.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "q7r8s9t0u1v2"
down_revision: Union[str, None] = "p6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE companies ADD COLUMN org_id UUID")
    op.execute(
        """
        UPDATE companies AS co
        SET org_id = c.org_id
        FROM clients AS c
        WHERE co.client_id = c.id
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM companies WHERE org_id IS NULL) THEN
            RAISE EXCEPTION 'companies.org_id backfill left null rows';
          END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE companies ALTER COLUMN org_id SET NOT NULL")
    op.execute(
        """
        ALTER TABLE companies
          ADD CONSTRAINT companies_org_id_fkey
          FOREIGN KEY (org_id) REFERENCES organisations (id) ON DELETE CASCADE
        """
    )
    op.execute(
        """
        ALTER TABLE companies
          ADD CONSTRAINT companies_org_id_id_key UNIQUE (org_id, id)
        """
    )
    op.execute("CREATE INDEX idx_companies_org_id ON companies (org_id)")
    op.execute("ALTER TABLE companies ADD COLUMN registered_office VARCHAR")
    op.execute("ALTER TABLE companies ADD COLUMN directors JSONB")
    op.execute("ALTER TABLE companies ADD COLUMN secretary VARCHAR")
    op.execute("ALTER TABLE companies ADD COLUMN financial_year_end DATE")
    op.execute("ALTER TABLE companies ADD COLUMN average_employees INTEGER")
    op.execute(
        """
        ALTER TABLE companies
          ADD CONSTRAINT companies_average_employees_check
          CHECK (average_employees IS NULL OR average_employees >= 0)
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION companies_org_id_matches_client()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          client_org uuid;
        BEGIN
          SELECT org_id INTO client_org FROM clients WHERE id = NEW.client_id;
          IF client_org IS NULL THEN
            RAISE EXCEPTION 'company client % not found', NEW.client_id;
          END IF;
          IF NEW.org_id IS NULL THEN
            NEW.org_id := client_org;
          ELSIF NEW.org_id IS DISTINCT FROM client_org THEN
            RAISE EXCEPTION
              'company org_id % does not match client org_id %',
              NEW.org_id, client_org;
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER companies_org_id_matches_client
        BEFORE INSERT OR UPDATE OF org_id, client_id ON companies
        FOR EACH ROW
        EXECUTE FUNCTION companies_org_id_matches_client();
        """
    )
    op.execute(
        """
        CREATE TABLE findraft_year_ends (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL REFERENCES organisations (id) ON DELETE CASCADE,
          company_id UUID NOT NULL,
          period_start DATE,
          period_end DATE NOT NULL,
          prior_year_validated BOOLEAN NOT NULL DEFAULT FALSE,
          pack_id VARCHAR(64) NOT NULL,
          pack_version VARCHAR(16) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT findraft_year_ends_period_key
            UNIQUE (org_id, company_id, period_end),
          CONSTRAINT findraft_year_ends_pin_key
            UNIQUE (id, org_id, company_id, pack_id, pack_version),
          CONSTRAINT findraft_year_ends_company_fk
            FOREIGN KEY (org_id, company_id)
            REFERENCES companies (org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_findraft_year_ends_org_id ON findraft_year_ends (org_id)"
    )
    op.execute(
        "CREATE INDEX idx_findraft_year_ends_company_id ON findraft_year_ends (company_id)"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_year_ends_reject_repin()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF NEW.pack_id IS DISTINCT FROM OLD.pack_id
             OR NEW.pack_version IS DISTINCT FROM OLD.pack_version THEN
            RAISE EXCEPTION
              'period already pinned to % % — create a new draft version instead of re-pinning',
              OLD.pack_id, OLD.pack_version;
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_year_ends_reject_repin
        BEFORE UPDATE OF pack_id, pack_version ON findraft_year_ends
        FOR EACH ROW
        EXECUTE FUNCTION findraft_year_ends_reject_repin();
        """
    )
    op.execute(
        """
        CREATE TABLE findraft_draft_versions (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL REFERENCES organisations (id) ON DELETE CASCADE,
          company_id UUID NOT NULL,
          year_end_id UUID NOT NULL,
          version_number INTEGER NOT NULL,
          pack_id VARCHAR(64) NOT NULL,
          pack_version VARCHAR(16) NOT NULL,
          status VARCHAR(16) NOT NULL DEFAULT 'draft',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT findraft_draft_versions_number_key
            UNIQUE (year_end_id, version_number),
          CONSTRAINT findraft_draft_versions_status_check
            CHECK (status IN ('draft', 'locked', 'final')),
          CONSTRAINT findraft_draft_versions_version_check
            CHECK (version_number >= 1),
          CONSTRAINT findraft_draft_versions_company_fk
            FOREIGN KEY (org_id, company_id)
            REFERENCES companies (org_id, id) ON DELETE CASCADE,
          CONSTRAINT findraft_draft_versions_pin_fk
            FOREIGN KEY (year_end_id, org_id, company_id, pack_id, pack_version)
            REFERENCES findraft_year_ends (id, org_id, company_id, pack_id, pack_version)
            ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_findraft_draft_versions_org_id ON findraft_draft_versions (org_id)"
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_draft_versions_year_end_id
          ON findraft_draft_versions (year_end_id)
        """
    )
    # SET ROLE findraft_app reports an unset custom GUC as '' rather than NULL.
    # NULLIF keeps that case from throwing on the uuid cast, so the predicate
    # matches no rows.
    op.execute("ALTER TABLE findraft_year_ends ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE findraft_year_ends FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY findraft_year_ends_org_isolation ON findraft_year_ends
          FOR ALL
          USING (
            org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          )
          WITH CHECK (
            org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          )
        """
    )
    op.execute("ALTER TABLE findraft_draft_versions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE findraft_draft_versions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY findraft_draft_versions_org_isolation ON findraft_draft_versions
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
            GRANT SELECT, INSERT, UPDATE, DELETE ON findraft_year_ends TO findraft_app;
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON findraft_draft_versions TO findraft_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS findraft_draft_versions")
    op.execute("DROP TABLE IF EXISTS findraft_year_ends")
    op.execute("DROP FUNCTION IF EXISTS findraft_year_ends_reject_repin()")
    op.execute(
        "DROP TRIGGER IF EXISTS companies_org_id_matches_client ON companies"
    )
    op.execute("DROP FUNCTION IF EXISTS companies_org_id_matches_client()")
    op.execute(
        "ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_average_employees_check"
    )
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS average_employees")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS financial_year_end")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS secretary")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS directors")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS registered_office")
    op.execute("DROP INDEX IF EXISTS idx_companies_org_id")
    op.execute(
        "ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_org_id_id_key"
    )
    op.execute(
        "ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_org_id_fkey"
    )
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS org_id")
