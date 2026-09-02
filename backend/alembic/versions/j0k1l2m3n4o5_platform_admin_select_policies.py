"""Platform admin SELECT policies for Owner-only /admin reads.

The findraft app role sets app.platform_admin=true only inside require_roles("owner")
admin handlers. Existing org-scoped policies remain unchanged; permissive SELECT
policies are OR'd so either path can grant access.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("waitlist_signups", "organisations", "users")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"""
            CREATE POLICY {table}_platform_admin_select ON {table}
              FOR SELECT
              USING (current_setting('app.platform_admin', true) = 'true')
            """
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"DROP POLICY IF EXISTS {table}_platform_admin_select ON {table}"
        )
