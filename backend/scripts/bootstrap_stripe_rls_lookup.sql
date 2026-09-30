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

-- Clerk user.updated webhooks arrive with only a clerk_user_id and must resolve
-- the user's org_id to set the RLS context before updating users. Under the
-- non-superuser findraft role that cross-org lookup is blocked by RLS, so use the
-- same SECURITY DEFINER + BYPASSRLS pattern as the Stripe lookups above. The
-- function only returns a single org_id for an exact-match on a high-entropy
-- Clerk user id (same accepted tradeoff as the Stripe grants).
DROP FUNCTION IF EXISTS app_find_org_id_for_clerk_user(varchar);

CREATE FUNCTION app_find_org_id_for_clerk_user(p_clerk_user_id varchar)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT org_id
  FROM users
  WHERE clerk_user_id = p_clerk_user_id
  LIMIT 1;
$$;

ALTER FUNCTION app_find_org_id_for_clerk_user(varchar)
  OWNER TO findraft_rls_bypass;

-- BYPASSRLS skips RLS policies but not table GRANTs.
GRANT SELECT ON users TO findraft_rls_bypass;

REVOKE ALL ON FUNCTION app_find_org_id_for_clerk_user(varchar) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_find_org_id_for_clerk_user(varchar) TO findraft;

COMMIT;
