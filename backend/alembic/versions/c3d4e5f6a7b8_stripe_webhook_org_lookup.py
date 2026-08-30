"""Alembic migration: restore fail-closed organisations_self_isolation.

An earlier draft of this revision briefly broadened RLS (null-safe self-isolation
plus a webhook SELECT policy gated on app.stripe_webhook). That was caught in
review and rejected — it would have allowed any findraft-role connection that
set the GUC to SELECT every organisations row.

This revision only restores the original self-isolation policy. The Stripe
customer/subscription → org_id lookup uses SECURITY DEFINER functions owned by
``findraft_rls_bypass`` (NOLOGIN BYPASSRLS), created by the superuser bootstrap
script — not by this findraft-role Alembic path:

  backend/scripts/bootstrap_stripe_rls_lookup.sql
  (see docs/runbooks/deployment.md)
"""

from alembic import op
from sqlalchemy import text

revision = "c3d4e5f6a7b8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the rejected webhook SELECT policy if a partial apply left it behind.
    op.execute(
        "DROP POLICY IF EXISTS organisations_stripe_webhook_lookup ON organisations"
    )
    op.execute("DROP POLICY IF EXISTS organisations_self_isolation ON organisations")
    op.execute(
        """
        CREATE POLICY organisations_self_isolation ON organisations
          FOR ALL
          USING (id = current_setting('app.current_org_id')::UUID)
        """
    )

    # Fail loudly if bootstrap was skipped — webhook org lookup will not work.
    conn = op.get_bind()
    role_exists = conn.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = 'findraft_rls_bypass'")
    ).scalar()
    fn_exists = conn.execute(
        text(
            "SELECT 1 FROM pg_proc WHERE proname = 'app_find_org_id_for_stripe_customer'"
        )
    ).scalar()
    if not role_exists or not fn_exists:
        raise RuntimeError(
            "findraft_rls_bypass / app_find_org_id_for_stripe_* missing. "
            "CREATE ROLE requires a superuser connection and cannot run via the "
            "normal findraft-role Alembic path. Run "
            "backend/scripts/bootstrap_stripe_rls_lookup.sql as a superuser "
            "(see docs/runbooks/deployment.md), then re-run this migration."
        )
    # GRANT EXECUTE on those functions → general findraft role lives in the
    # bootstrap script (deliberate tradeoff; documented there + deployment.md).
    # Do not move CREATE ROLE / BYPASSRLS setup into this findraft-role migration.


def downgrade() -> None:
    # Leave self_isolation as originally designed; bootstrap objects are
    # removed separately if needed (DROP FUNCTION / DROP ROLE as superuser).
    pass
