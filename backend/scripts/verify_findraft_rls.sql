-- Verify the findraft role is subject to RLS (not superuser / bypass).
-- Run as the findraft login role:
--   psql "$FINDRAFT_DATABASE_URL_SYNC" -f backend/scripts/verify_findraft_rls.sql

\set ON_ERROR_STOP on

\echo '=== role flags (must be superuser=f, bypassrls=f) ==='
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles
WHERE rolname = current_user;

\echo '=== clients visible with fake org (expect 0 rows) ==='
BEGIN;
SET LOCAL app.current_org_id = '00000000-0000-0000-0000-000000000000';
SELECT * FROM clients;
SELECT count(*) AS client_rows_with_fake_org FROM clients;
ROLLBACK;
