"""Add companies table between clients and trial_balances.

Introduces ``companies`` as the entity that owns functional currency, materiality
thresholds, and TB/mapping rows. Each existing client receives exactly one
company row (1:1 data migration); ``trial_balances`` and ``account_mappings`` FKs
move from ``client_id`` to ``company_id``.

RLS:
  - companies: one-hop via client_id -> clients.org_id
  - trial_balances, account_mappings: two-hop via company_id -> companies -> clients
  - downstream TB children: one additional companies join (same pattern as the
    existing financial_statements / statement_line_items chain)

NOT APPLIED — design for review only.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c0"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables whose RLS policies join trial_balances -> clients today and need the
# companies hop after this migration (deepest first for clean downgrade re-create).
_TB_CHILD_RLS_TABLES = (
    "commentary_feedback",
    "statement_line_items",
    "processing_jobs",
    "exports",
    "risk_flags",
    "variance_analyses",
    "financial_statements",
)


def _drop_org_isolation_policy(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {table}_org_isolation ON {table}")


def _enable_companies_rls() -> None:
    op.execute("ALTER TABLE companies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE companies FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY companies_org_isolation ON companies
          FOR ALL
          USING (
            client_id IN (
              SELECT id FROM clients
              WHERE org_id = current_setting('app.current_org_id')::UUID
            )
          )
        """
    )


def _enable_trial_balances_rls() -> None:
    op.execute("ALTER TABLE trial_balances ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE trial_balances FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY trial_balances_org_isolation ON trial_balances
          FOR ALL
          USING (
            company_id IN (
              SELECT co.id FROM companies co
              JOIN clients c ON co.client_id = c.id
              WHERE c.org_id = current_setting('app.current_org_id')::UUID
            )
          )
        """
    )


def _enable_account_mappings_rls() -> None:
    op.execute("ALTER TABLE account_mappings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE account_mappings FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY account_mappings_org_isolation ON account_mappings
          FOR ALL
          USING (
            company_id IN (
              SELECT co.id FROM companies co
              JOIN clients c ON co.client_id = c.id
              WHERE c.org_id = current_setting('app.current_org_id')::UUID
            )
          )
        """
    )


def _enable_tb_child_rls(table: str) -> None:
    """Two-hop TB children: tb -> companies -> clients."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_org_isolation ON {table}
          FOR ALL
          USING (
            tb_id IN (
              SELECT tb.id FROM trial_balances tb
              JOIN companies co ON tb.company_id = co.id
              JOIN clients c ON co.client_id = c.id
              WHERE c.org_id = current_setting('app.current_org_id')::UUID
            )
          )
        """
    )


def _enable_statement_line_items_rls() -> None:
    """Three-hop: statement_line_items -> financial_statements -> trial_balances -> companies -> clients."""
    op.execute("ALTER TABLE statement_line_items ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY statement_line_items_org_isolation ON statement_line_items
          FOR ALL
          USING (
            statement_id IN (
              SELECT fs.id FROM financial_statements fs
              JOIN trial_balances tb ON fs.tb_id = tb.id
              JOIN companies co ON tb.company_id = co.id
              JOIN clients c ON co.client_id = c.id
              WHERE c.org_id = current_setting('app.current_org_id')::UUID
            )
          )
        """
    )


def _enable_commentary_feedback_rls() -> None:
    """Three-hop: commentary_feedback -> variance_analyses -> trial_balances -> companies -> clients."""
    op.execute("ALTER TABLE commentary_feedback ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY commentary_feedback_org_isolation ON commentary_feedback
          FOR ALL
          USING (
            variance_id IN (
              SELECT va.id FROM variance_analyses va
              JOIN trial_balances tb ON va.tb_id = tb.id
              JOIN companies co ON tb.company_id = co.id
              JOIN clients c ON co.client_id = c.id
              WHERE c.org_id = current_setting('app.current_org_id')::UUID
            )
          )
        """
    )


def _disable_rls_for_data_migration() -> None:
    """Alembic runs without app.current_org_id; bypass RLS for backfill DML only.

    Exact SQL (one statement per table, executed in order):
      ALTER TABLE clients DISABLE ROW LEVEL SECURITY;
      ALTER TABLE trial_balances DISABLE ROW LEVEL SECURITY;
      ALTER TABLE account_mappings DISABLE ROW LEVEL SECURITY;

    RLS is NOT re-enabled here. It stays off until new policies exist at the
    end of upgrade()/downgrade(), so there is no window where RLS is on but
    policies are missing or stale.
    """
    for table in ("clients", "trial_balances", "account_mappings"):
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def _ensure_clients_rls_with_force() -> None:
    """clients policy is unchanged; re-apply ENABLE + FORCE after backfill."""
    op.execute("ALTER TABLE clients ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE clients FORCE ROW LEVEL SECURITY")


def _assert_rls_flags_active(tables: tuple[str, ...]) -> None:
    """Fail the migration if relrowsecurity or relforcerowsecurity is false."""
    table_list = ", ".join(f"'{t}'" for t in tables)
    op.execute(
        f"""
        DO $$
        DECLARE
          rec RECORD;
        BEGIN
          FOR rec IN
            SELECT c.relname,
                   c.relrowsecurity,
                   c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname IN ({table_list})
          LOOP
            IF NOT rec.relrowsecurity OR NOT rec.relforcerowsecurity THEN
              RAISE EXCEPTION
                'RLS not fully active on % (relrowsecurity=%, relforcerowsecurity=%)',
                rec.relname, rec.relrowsecurity, rec.relforcerowsecurity;
            END IF;
          END LOOP;
        END $$;
        """
    )


def _assert_migration_integrity() -> None:
    """Fail the migration if backfill left orphans or broke 1:1 client->company."""
    op.execute(
        """
        DO $$
        DECLARE
          client_count INTEGER;
          company_count INTEGER;
          orphan_clients INTEGER;
          orphan_tbs INTEGER;
          orphan_mappings INTEGER;
        BEGIN
          SELECT COUNT(*) INTO client_count FROM clients;
          SELECT COUNT(*) INTO company_count FROM companies;
          IF client_count <> company_count THEN
            RAISE EXCEPTION
              'companies backfill count mismatch: % clients, % companies',
              client_count, company_count;
          END IF;

          SELECT COUNT(*) INTO orphan_clients
          FROM clients c
          LEFT JOIN companies co ON co.client_id = c.id
          WHERE co.id IS NULL;
          IF orphan_clients > 0 THEN
            RAISE EXCEPTION '% clients have no company row', orphan_clients;
          END IF;

          SELECT COUNT(*) INTO orphan_tbs
          FROM trial_balances WHERE company_id IS NULL;
          IF orphan_tbs > 0 THEN
            RAISE EXCEPTION '% trial_balances rows missing company_id', orphan_tbs;
          END IF;

          SELECT COUNT(*) INTO orphan_mappings
          FROM account_mappings WHERE company_id IS NULL;
          IF orphan_mappings > 0 THEN
            RAISE EXCEPTION '% account_mappings rows missing company_id', orphan_mappings;
          END IF;
        END $$;
        """
    )


def _assert_downgrade_safe() -> None:
    """Abort downgrade when any client has more than one company (lossy collapse)."""
    op.execute(
        """
        DO $$
        DECLARE
          multi_company_clients INTEGER;
        BEGIN
          SELECT COUNT(*) INTO multi_company_clients
          FROM (
            SELECT client_id
            FROM companies
            GROUP BY client_id
            HAVING COUNT(*) > 1
          ) multi;

          IF multi_company_clients > 0 THEN
            RAISE EXCEPTION
              'Cannot downgrade: % clients have multiple companies. '
              'Manually consolidate or delete extra companies before downgrading.',
              multi_company_clients;
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create companies (empty)
    # ------------------------------------------------------------------
    op.create_table(
        "companies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "functional_currency",
            sa.String(length=3),
            server_default=sa.text("'GBP'"),
            nullable=False,
        ),
        sa.Column("company_number", sa.String(), nullable=True),
        sa.Column("industry", sa.String(), nullable=True),
        sa.Column(
            "materiality_threshold_pct",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("10.00"),
            nullable=False,
        ),
        sa.Column(
            "materiality_threshold_abs",
            sa.Numeric(precision=19, scale=2),
            server_default=sa.text("1000.00"),
            nullable=False,
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["client_id"], ["clients.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_companies_client_id", "companies", ["client_id"], unique=False)
    op.create_index(
        "idx_companies_client_deleted",
        "companies",
        ["client_id", "is_deleted"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 2. Data migration: one company per existing client
    # ------------------------------------------------------------------
    _disable_rls_for_data_migration()
    op.execute(
        """
        INSERT INTO companies (
            id,
            client_id,
            name,
            functional_currency,
            company_number,
            industry,
            materiality_threshold_pct,
            materiality_threshold_abs,
            is_deleted,
            deleted_at,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            c.id,
            c.name,
            c.functional_currency,
            c.company_number,
            c.industry,
            c.materiality_threshold_pct,
            c.materiality_threshold_abs,
            c.is_deleted,
            c.deleted_at,
            c.created_at,
            c.updated_at
        FROM clients c
        """
    )

    # ------------------------------------------------------------------
    # 3. Add nullable company_id FK columns
    # ------------------------------------------------------------------
    op.add_column(
        "trial_balances",
        sa.Column("company_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "account_mappings",
        sa.Column("company_id", sa.UUID(), nullable=True),
    )

    # ------------------------------------------------------------------
    # 4. Repoint existing rows via client_id -> companies.client_id
    # ------------------------------------------------------------------
    op.execute(
        """
        UPDATE trial_balances tb
        SET company_id = co.id
        FROM companies co
        WHERE co.client_id = tb.client_id
        """
    )
    op.execute(
        """
        UPDATE account_mappings am
        SET company_id = co.id
        FROM companies co
        WHERE co.client_id = am.client_id
        """
    )

    _assert_migration_integrity()

    # ------------------------------------------------------------------
    # 5. Drop RLS policies that reference trial_balances.client_id
    #     (tables stay RLS-disabled until step 9 recreates policies)
    # ------------------------------------------------------------------
    _drop_org_isolation_policy("commentary_feedback")
    _drop_org_isolation_policy("statement_line_items")
    for table in _TB_CHILD_RLS_TABLES:
        if table not in ("commentary_feedback", "statement_line_items"):
            _drop_org_isolation_policy(table)
    _drop_org_isolation_policy("trial_balances")
    _drop_org_isolation_policy("account_mappings")

    # ------------------------------------------------------------------
    # 6. trial_balances: client_id -> company_id
    # ------------------------------------------------------------------
    op.drop_constraint(
        "trial_balances_client_id_period_end_key",
        "trial_balances",
        type_="unique",
    )
    op.drop_index("idx_trial_balances_client_period", table_name="trial_balances")
    op.drop_index("idx_trial_balances_client_id", table_name="trial_balances")
    op.drop_constraint(
        "trial_balances_client_id_fkey",
        "trial_balances",
        type_="foreignkey",
    )
    op.drop_column("trial_balances", "client_id")

    op.alter_column("trial_balances", "company_id", nullable=False)
    op.create_foreign_key(
        "trial_balances_company_id_fkey",
        "trial_balances",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "trial_balances_company_id_period_end_key",
        "trial_balances",
        ["company_id", "period_end"],
    )
    op.create_index(
        "idx_trial_balances_company_id",
        "trial_balances",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "idx_trial_balances_company_period",
        "trial_balances",
        ["company_id", "period_end"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 7. account_mappings: client_id -> company_id
    # ------------------------------------------------------------------
    op.drop_constraint(
        "account_mappings_client_id_source_code_source_name_key",
        "account_mappings",
        type_="unique",
    )
    op.drop_index(
        "idx_account_mappings_client_confirmed",
        table_name="account_mappings",
    )
    op.drop_index("idx_account_mappings_client_id", table_name="account_mappings")
    op.drop_constraint(
        "account_mappings_client_id_fkey",
        "account_mappings",
        type_="foreignkey",
    )
    op.drop_column("account_mappings", "client_id")

    op.alter_column("account_mappings", "company_id", nullable=False)
    op.create_foreign_key(
        "account_mappings_company_id_fkey",
        "account_mappings",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "account_mappings_company_id_source_code_source_name_key",
        "account_mappings",
        ["company_id", "source_code", "source_name"],
    )
    op.create_index(
        "idx_account_mappings_company_id",
        "account_mappings",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "idx_account_mappings_company_confirmed",
        "account_mappings",
        ["company_id", "is_confirmed"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 8. Simplify clients (practice-level fields move to companies)
    # ------------------------------------------------------------------
    op.drop_column("clients", "company_number")
    op.drop_column("clients", "industry")
    op.drop_column("clients", "functional_currency")
    op.drop_column("clients", "materiality_threshold_pct")
    op.drop_column("clients", "materiality_threshold_abs")

    # ------------------------------------------------------------------
    # 9. RLS: ENABLE + FORCE + new policies (atomic end state before commit)
    # ------------------------------------------------------------------
    _enable_companies_rls()
    _enable_trial_balances_rls()
    _enable_account_mappings_rls()
    _ensure_clients_rls_with_force()
    for table in _TB_CHILD_RLS_TABLES:
        if table == "statement_line_items":
            _enable_statement_line_items_rls()
        elif table == "commentary_feedback":
            _enable_commentary_feedback_rls()
        else:
            _enable_tb_child_rls(table)

    _assert_rls_flags_active(("companies", "trial_balances", "account_mappings"))


def downgrade() -> None:
    """Reverse schema only when every client still has exactly one company.

    Raises if any client has multiple companies — downgrade must not silently
    discard extra company rows.
    """

    # ------------------------------------------------------------------
    # 1. Drop new RLS policies
    # ------------------------------------------------------------------
    _drop_org_isolation_policy("companies")
    op.execute("ALTER TABLE companies NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE companies DISABLE ROW LEVEL SECURITY")

    _drop_org_isolation_policy("commentary_feedback")
    _drop_org_isolation_policy("statement_line_items")
    for table in _TB_CHILD_RLS_TABLES:
        if table not in ("commentary_feedback", "statement_line_items"):
            _drop_org_isolation_policy(table)
    _drop_org_isolation_policy("trial_balances")
    _drop_org_isolation_policy("account_mappings")

    # ------------------------------------------------------------------
    # 2. Guard: refuse lossy downgrade when multi-company clients exist
    # ------------------------------------------------------------------
    _assert_downgrade_safe()

    # ------------------------------------------------------------------
    # 3. Restore clients columns (nullable until backfill)
    # ------------------------------------------------------------------
    _disable_rls_for_data_migration()
    op.add_column(
        "clients",
        sa.Column("company_number", sa.String(), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("industry", sa.String(), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column(
            "functional_currency",
            sa.String(length=3),
            server_default=sa.text("'GBP'"),
            nullable=True,
        ),
    )
    op.add_column(
        "clients",
        sa.Column(
            "materiality_threshold_pct",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("10.00"),
            nullable=True,
        ),
    )
    op.add_column(
        "clients",
        sa.Column(
            "materiality_threshold_abs",
            sa.Numeric(precision=19, scale=2),
            server_default=sa.text("1000.00"),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE clients c
        SET
            company_number = co.company_number,
            industry = co.industry,
            functional_currency = co.functional_currency,
            materiality_threshold_pct = co.materiality_threshold_pct,
            materiality_threshold_abs = co.materiality_threshold_abs,
            is_deleted = co.is_deleted,
            deleted_at = co.deleted_at
        FROM companies co
        WHERE co.client_id = c.id
        """
    )

    op.alter_column("clients", "functional_currency", nullable=False)
    op.alter_column("clients", "materiality_threshold_pct", nullable=False)
    op.alter_column("clients", "materiality_threshold_abs", nullable=False)

    # ------------------------------------------------------------------
    # 4. account_mappings: company_id -> client_id
    # ------------------------------------------------------------------
    op.add_column(
        "account_mappings",
        sa.Column("client_id", sa.UUID(), nullable=True),
    )
    op.execute(
        """
        UPDATE account_mappings am
        SET client_id = co.client_id
        FROM companies co
        WHERE co.id = am.company_id
        """
    )

    op.drop_constraint(
        "account_mappings_company_id_source_code_source_name_key",
        "account_mappings",
        type_="unique",
    )
    op.drop_index(
        "idx_account_mappings_company_confirmed",
        table_name="account_mappings",
    )
    op.drop_index("idx_account_mappings_company_id", table_name="account_mappings")
    op.drop_constraint(
        "account_mappings_company_id_fkey",
        "account_mappings",
        type_="foreignkey",
    )
    op.drop_column("account_mappings", "company_id")

    op.alter_column("account_mappings", "client_id", nullable=False)
    op.create_foreign_key(
        "account_mappings_client_id_fkey",
        "account_mappings",
        "clients",
        ["client_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "account_mappings_client_id_source_code_source_name_key",
        "account_mappings",
        ["client_id", "source_code", "source_name"],
    )
    op.create_index(
        "idx_account_mappings_client_id",
        "account_mappings",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        "idx_account_mappings_client_confirmed",
        "account_mappings",
        ["client_id", "is_confirmed"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 5. trial_balances: company_id -> client_id
    # ------------------------------------------------------------------
    op.add_column(
        "trial_balances",
        sa.Column("client_id", sa.UUID(), nullable=True),
    )
    op.execute(
        """
        UPDATE trial_balances tb
        SET client_id = co.client_id
        FROM companies co
        WHERE co.id = tb.company_id
        """
    )

    op.drop_constraint(
        "trial_balances_company_id_period_end_key",
        "trial_balances",
        type_="unique",
    )
    op.drop_index("idx_trial_balances_company_period", table_name="trial_balances")
    op.drop_index("idx_trial_balances_company_id", table_name="trial_balances")
    op.drop_constraint(
        "trial_balances_company_id_fkey",
        "trial_balances",
        type_="foreignkey",
    )
    op.drop_column("trial_balances", "company_id")

    op.alter_column("trial_balances", "client_id", nullable=False)
    op.create_foreign_key(
        "trial_balances_client_id_fkey",
        "trial_balances",
        "clients",
        ["client_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "trial_balances_client_id_period_end_key",
        "trial_balances",
        ["client_id", "period_end"],
    )
    op.create_index(
        "idx_trial_balances_client_id",
        "trial_balances",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        "idx_trial_balances_client_period",
        "trial_balances",
        ["client_id", "period_end"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 6. Drop companies
    # ------------------------------------------------------------------
    op.drop_index("idx_companies_client_deleted", table_name="companies")
    op.drop_index("idx_companies_client_id", table_name="companies")
    op.drop_table("companies")

    # ------------------------------------------------------------------
    # 7. Restore original RLS policies + ENABLE/FORCE (tables were disabled
    #    during backfill; policies recreated here before commit)
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE trial_balances ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE trial_balances FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE account_mappings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE account_mappings FORCE ROW LEVEL SECURITY")
    _ensure_clients_rls_with_force()
    op.execute(
        """
        CREATE POLICY trial_balances_org_isolation ON trial_balances
          FOR ALL
          USING (
            client_id IN (
              SELECT id FROM clients
              WHERE org_id = current_setting('app.current_org_id')::UUID
            )
          )
        """
    )
    op.execute(
        """
        CREATE POLICY account_mappings_org_isolation ON account_mappings
          FOR ALL
          USING (
            client_id IN (
              SELECT id FROM clients
              WHERE org_id = current_setting('app.current_org_id')::UUID
            )
          )
        """
    )
    for table in _TB_CHILD_RLS_TABLES:
        if table == "statement_line_items":
            op.execute(
                """
                CREATE POLICY statement_line_items_org_isolation ON statement_line_items
                  FOR ALL
                  USING (
                    statement_id IN (
                      SELECT fs.id FROM financial_statements fs
                      JOIN trial_balances tb ON fs.tb_id = tb.id
                      JOIN clients c ON tb.client_id = c.id
                      WHERE c.org_id = current_setting('app.current_org_id')::UUID
                    )
                  )
                """
            )
        elif table == "commentary_feedback":
            op.execute(
                """
                CREATE POLICY commentary_feedback_org_isolation ON commentary_feedback
                  FOR ALL
                  USING (
                    variance_id IN (
                      SELECT va.id FROM variance_analyses va
                      JOIN trial_balances tb ON va.tb_id = tb.id
                      JOIN clients c ON tb.client_id = c.id
                      WHERE c.org_id = current_setting('app.current_org_id')::UUID
                    )
                  )
                """
            )
        else:
            op.execute(
                f"""
                CREATE POLICY {table}_org_isolation ON {table}
                  FOR ALL
                  USING (
                    tb_id IN (
                      SELECT tb.id FROM trial_balances tb
                      JOIN clients c ON tb.client_id = c.id
                      WHERE c.org_id = current_setting('app.current_org_id')::UUID
                    )
                  )
                """
            )
