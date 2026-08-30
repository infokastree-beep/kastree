"""Force RLS for table owners (defence-in-depth).

PostgreSQL skips RLS for the table owner unless FORCE ROW LEVEL SECURITY is set.
The app role owns these tables, so without FORCE the organisations_self_isolation
chicken-and-egg bootstrap (and all other policies) would never actually run.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "5698f66e1e9c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_TABLES = (
    "clients",
    "audit_logs",
    "notifications",
    "archived_records",
    "users",
    "subscription_events",
    "organisations",
    "trial_balances",
    "account_mappings",
    "financial_statements",
    "variance_analyses",
    "risk_flags",
    "exports",
    "processing_jobs",
    "statement_line_items",
    "commentary_feedback",
)


def upgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
