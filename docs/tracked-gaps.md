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

## Tier 4 OpenAI in sync BackgroundTasks (event-loop blocking)

`run_parse_and_map_job` (`backend/app/services/tb_pipeline.py`) invokes Tier 4
mapping via synchronous `OpenAI()` calls inside a sync `BackgroundTasks`
function. Fine when the call fails fast (e.g. missing `OPENAI_API_KEY`, as in
the walkthrough), but a genuine risk of blocking the entire async event loop if
a real key is set and a call is slow to respond or hangs.

**Before Tier 4 is used with a real key in anything beyond a one-off local
test:** make the LLM path properly async (e.g. `asyncio.to_thread` / executor
at minimum) or move parse/map to a real task queue per the Celery/Redis Month
3+ plan. See also `backend/app/services/mapper.py` (`apply_llm_tie_breaker`).

