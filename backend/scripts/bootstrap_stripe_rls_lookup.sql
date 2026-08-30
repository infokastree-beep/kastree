-- bootstrap_stripe_rls_lookup.sql
--
-- Superuser-only setup for Stripe webhook org resolution under FORCE RLS.
-- The normal findraft-role Alembic path cannot CREATE ROLE … BYPASSRLS.
--
-- Run once per environment (fresh staging, DR restore, new prod DB), the same
-- class of required manual step as scripts/configure_s3_lifecycle.py:
--
--   sudo -u postgres psql -d findraft_dev -f backend/scripts/bootstrap_stripe_rls_lookup.sql
--   # or, with a cloud superuser URL:
--   psql "$DATABASE_SUPERUSER_URL" -f backend/scripts/bootstrap_stripe_rls_lookup.sql
--
-- Skipping this leaves /webhooks/stripe unable to resolve org_id from
-- stripe_customer_id / stripe_subscription_id (obscure lookup failure).
-- See docs/runbooks/deployment.md.

BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'findraft_rls_bypass') THEN
    CREATE ROLE findraft_rls_bypass NOLOGIN BYPASSRLS;
  END IF;
END
$$;

DROP FUNCTION IF EXISTS app_find_org_id_for_stripe_customer(varchar);
DROP FUNCTION IF EXISTS app_find_org_id_for_stripe_subscription(varchar);

CREATE FUNCTION app_find_org_id_for_stripe_customer(p_customer_id varchar)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT id
  FROM organisations
  WHERE stripe_customer_id = p_customer_id
  LIMIT 1;
$$;

CREATE FUNCTION app_find_org_id_for_stripe_subscription(p_subscription_id varchar)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT id
  FROM organisations
  WHERE stripe_subscription_id = p_subscription_id
  LIMIT 1;
$$;

ALTER FUNCTION app_find_org_id_for_stripe_customer(varchar)
  OWNER TO findraft_rls_bypass;
ALTER FUNCTION app_find_org_id_for_stripe_subscription(varchar)
  OWNER TO findraft_rls_bypass;

-- BYPASSRLS skips RLS policies but not table GRANTs.
GRANT SELECT ON organisations TO findraft_rls_bypass;

REVOKE ALL ON FUNCTION app_find_org_id_for_stripe_customer(varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_find_org_id_for_stripe_subscription(varchar) FROM PUBLIC;

-- EXECUTE is granted to the general findraft role (not a webhook-specific role)
-- as a deliberate, accepted tradeoff: these functions only ever return a single
-- uuid via exact-match lookup on a high-entropy Stripe ID, so the practical
-- risk of this being reachable from other findraft-role code paths is low —
-- but it IS a wider grant than strictly necessary. A future reviewer should
-- know that was a conscious choice, not an oversight. (See also
-- docs/runbooks/deployment.md.)
GRANT EXECUTE ON FUNCTION app_find_org_id_for_stripe_customer(varchar)
  TO findraft;
GRANT EXECUTE ON FUNCTION app_find_org_id_for_stripe_subscription(varchar)
  TO findraft;

COMMIT;
