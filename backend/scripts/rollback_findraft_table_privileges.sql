-- Roll back backend/scripts/findraft_table_privileges.sql.
--
-- Run as the same superuser that applied the migration, after
-- `alembic downgrade d0e1f2a3b4` or instead of that downgrade when the
-- schema change must stay and only the grants should return.
--
-- Sequences are not changed.
--
--   psql "$DATABASE_URL_SYNC" -v ON_ERROR_STOP=1 \
--     -f backend/scripts/rollback_findraft_table_privileges.sql

\set ON_ERROR_STOP on

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO findraft;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO findraft;
