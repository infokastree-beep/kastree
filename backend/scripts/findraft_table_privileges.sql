-- Least privilege for the production login named findraft.
--
-- Safe to run more than once, including after a later migration. It never
-- grants UPDATE or DELETE on an append-only table, and it never grants
-- TRUNCATE, REFERENCES, or TRIGGER.
--
-- Sequences are not touched. Leave GRANT ALL ON SEQUENCES as it stands.
--
-- Version header tables keep UPDATE. findraft_tb_versions_immutable and
-- findraft_fa_versions_immutable allow an update while status is pending
-- (the import worker moves pending to ready or failed). They are not the
-- fully immutable triggers below. findraft_draft_status_guard is a status
-- guard, not an append-only trigger, so findraft_draft_versions keeps
-- SELECT, INSERT, UPDATE, and DELETE.
--
-- Fully immutable trigger names matched here:
--   %append_only
--   %_lines_immutable          (findraft_tb_lines, findraft_fa_lines)
--   findraft_confirmed_mappings_immutable
-- Tables with no such trigger that are still append-only by design:
--   archived_records, subscription_events, findraft_draft_operations

DO $findraft_table_privileges$
DECLARE
  rel text;
  restricted boolean;
  append_only text[] := ARRAY[
    'audit_logs',
    'archived_records',
    'subscription_events',
    'findraft_draft_operations',
    'findraft_tb_lines',
    'findraft_fa_lines',
    'findraft_confirmed_mappings'
  ];
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'findraft') THEN
    RAISE EXCEPTION 'role findraft does not exist';
  END IF;

  EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM findraft';
  EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO findraft';

  FOR rel IN
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
    ORDER BY c.relname
  LOOP
    EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM findraft', rel);
    restricted := rel = ANY (append_only) OR EXISTS (
      SELECT 1
      FROM pg_trigger t
      JOIN pg_proc p ON p.oid = t.tgfoid
      WHERE t.tgrelid = format('public.%I', rel)::regclass
        AND NOT t.tgisinternal
        AND (
          p.proname LIKE '%append_only'
          OR p.proname LIKE '%\_lines\_immutable' ESCAPE '\'
          OR p.proname = 'findraft_confirmed_mappings_immutable'
        )
    );
    IF restricted THEN
      EXECUTE format(
        'GRANT SELECT, INSERT ON TABLE public.%I TO findraft',
        rel
      );
    ELSE
      EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO findraft',
        rel
      );
    END IF;
    EXECUTE format(
      'REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLE public.%I FROM findraft',
      rel
    );
  END LOOP;
END
$findraft_table_privileges$;
