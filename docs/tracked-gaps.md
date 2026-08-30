# Tracked gaps

Known implementation gaps that are **accepted for now** but should not be forgotten.
Review this list before claiming a feature area is complete.

## Archival write paths

Only **clients** soft-delete currently writes to `archived_records`. See
`backend/app/routers/clients.py` module docstring for detail.

| Entity | Gap |
|--------|-----|
| `trial_balances` | `DELETE /trial-balances/{id}` specified in Product Spec §10.2 / §12.2 (snapshot on delete) — no delete handler or archive write yet. |
| `financial_statements` | `archived_records.entity_type` includes statements, but no delete/archive write path (statements are replaced in place on regenerate; no soft-delete column). |

## Clerk webhook payload persistence

Clerk webhook payloads are **not persisted** anywhere (unlike Stripe's
`subscription_events` table). After processing, the only audit trail is
structured application logs (`clerk_webhook_*` events in `app/routers/auth.py`).

**Not urgent.** If audit or replay becomes necessary, add a `clerk_webhook_events`
table mirroring `subscription_events`: Svix message id, event type, full payload
(JSONB), `processed_at`, and optional handler outcome. Until then, historical
delivery `type` fields cannot be reconstructed from the database alone.

## Webhook concurrency (test coverage)

`provision_first_signup` handles concurrent duplicate `organization.created`
deliveries via `IntegrityError` recovery, but the HTTP idempotency test only
covers the serialised “org already exists” path — not true parallel delivery.
See `backend/tests/test_api.py` (`test_duplicate_provision_first_signup_*`).
