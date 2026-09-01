-- Provision the non-superuser application role for production (Railway, etc.).
--
-- Run as database superuser AFTER alembic upgrade head (tables must exist):
--   psql "$DATABASE_URL_SYNC" -v findraft_password=YOUR_STRONG_PASSWORD \
--     -v database_name=railway \
--     -f backend/scripts/provision_findraft_app_role.sql
--
-- The role name MUST be "findraft" — bootstrap_stripe_rls_lookup.sql grants
-- EXECUTE on Stripe org-lookup functions to this role.

\set ON_ERROR_STOP on

SELECT CASE
  WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'findraft') THEN
    format(
      'CREATE ROLE findraft WITH LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS',
      :'findraft_password'
    )
  ELSE
    format(
      'ALTER ROLE findraft WITH LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS',
      :'findraft_password'
    )
END
\gexec

GRANT CONNECT ON DATABASE :"database_name" TO findraft;
GRANT USAGE ON SCHEMA public TO findraft;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO findraft;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO findraft;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO findraft;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO findraft;
