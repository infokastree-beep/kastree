# Kastree Convert — standalone product design

Status: **BUILT** (2026-09-09). Subscriber Upload flow remains untouched.
Live routes: `/solutions/convert`, success/cancel; API `/solutions/convert/*`.
Price: **€19** one-time (`STRIPE_PRICE_ID_CONVERT`).

## Problem / shape

A one-time, no-account tool: upload a trial-balance PDF (or Excel/CSV) → review
extracted rows → pay once → download structured Excel/CSV. Entry via marketing
**Solutions → Convert**, separate from the Kastree app nav.

**MVP scope:** trial balance conversion only (reuses Phase 1). General ledger →
TB is Phase 3 and is **not** built here; the Convert page accepts TB documents
and labels GL as “coming soon” so we do not invent ledger math.

## Pricing

| Item | Amount | Stripe mode |
|------|--------|-------------|
| **Kastree Convert — one conversion** | **€19.00** flat | `mode: "payment"` (one-time) |

Rationale: well below Starter (€69/mo) so it does not substitute for a
subscription; high enough to deter OCR abuse. Env: `STRIPE_PRICE_ID_CONVERT`.

## Routes (frontend)

| Path | Auth | Purpose |
|------|------|---------|
| `/solutions/convert` | **Public** | Upload → extract/review → pay CTA |
| `/solutions/convert/success` | **Public** | Post-Checkout; verify session; download |
| `/solutions/convert/cancel` | **Public** | Abandoned Checkout; return to tool |

Nav: `MarketingNav` gains a **Solutions** dropdown with **Convert** (and room
for future entries). Not added to dashboard `(dashboard)` nav / `ProductSwitcher`.

Middleware: do **not** add these paths to `isDashboardRoute` — public by omission.

## Routes (backend)

New router `POST/GET /solutions/convert/*` — **no Clerk JWT**. Rate-limited.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/solutions/convert/extract` | PDF only → Phase 1 `extract_trial_balance_from_pdf` (same engine) |
| `POST` | `/solutions/convert/checkout` | Body: confirmed rows + email optional → persist ephemeral job → Stripe Checkout `mode=payment` |
| `GET` | `/solutions/convert/status` | `?session_id=` → paid? + download ready |
| `GET` | `/solutions/convert/download` | `?session_id=` → stream `.xlsx` after payment verified |

Existing `POST /trial-balances/extract-pdf` and `/trial-balances/upload` and
`POST /billing/checkout` (**subscription**) stay unchanged.

## Checkout flow

```
[Public Convert page]
   │  upload PDF
   ▼
POST /solutions/convert/extract   (rate limit; no auth)
   │  rows + method + warnings
   ▼
[Review UI — reuse PdfExtractReview pattern]
   │  user confirms/edits
   ▼
POST /solutions/convert/checkout  { rows, customer_email? }
   │  store conversion_jobs (pending_payment)
   │  Stripe Checkout Session mode=payment
   │  metadata: { product: "kastree_convert", conversion_id }
   ▼
[Stripe hosted Checkout — €19]
   │  success_url → /solutions/convert/success?session_id={CHECKOUT_SESSION_ID}
   │  cancel_url  → /solutions/convert/cancel
   ▼
Webhook checkout.session.completed
   │  if metadata.product == kastree_convert → mark job paid
   │  (does NOT touch organisations.subscription_*)
   ▼
[Success page] GET download → .xlsx
   + soft upsell: “Want this in full statements? Create a Kastree account”
```

**Payment verification for download:** prefer webhook-marked `paid`; also accept
live Stripe retrieve of session (`payment_status=paid`) so success page works
before webhook latency.

## How Phase 1 engine is reused

- Import `extract_trial_balance_from_pdf` / `rows_to_csv_bytes` from
  `app.services.pdf_tb_extract` — **no duplicate extraction logic**.
- Excel/CSV TB: reuse `parse_tb_file` for preview rows, then same review + pay +
  download path (no OCR).
- Mandatory review: download Checkout is only created after explicit confirm of
  the review table (same product rule as in-flow).
- Output: OpenPyXL `.xlsx` (Account Code / Name / Debit / Credit) — structured
  file delivery, not mapping/statements.

## Data model (ephemeral)

Table `standalone_conversions` (append-ish; TTL cleanup later):

- `id` UUID PK  
- `status` `pending_payment` | `paid` | `expired`  
- `rows` JSONB (confirmed review rows)  
- `stripe_session_id` UNIQUE nullable  
- `customer_email` nullable  
- `download_count` int  
- `created_at`, `paid_at`, `expires_at` (e.g. 24h after create / 48h after pay)

No `org_id` — these are not RLS org rows. Prefer no RLS or a dedicated policy
that denies normal app roles (service role / backend-only access).

## Explicit non-goals (this build)

- Do **not** modify `UploadForm` / in-flow PDF path for subscribers.  
- Do **not** call `/trial-balances/upload` or create `trial_balances`.  
- Do **not** implement GL→TB (Phase 3).  
- Do **not** change subscription Checkout / tier webhook writers.  
- Do **not** require Clerk sign-in for Convert.

## Abuse controls

- Extract: rate limit per IP (stricter than waitlist; e.g. 5/hour).  
- Checkout: rate limit per IP (e.g. 10/hour).  
- Max upload 50MB; PDF magic check; same Phase 1 fail-closed extract errors.  
- Paid download: Stripe session must be `paid` and bound to conversion id.

## Soft upsell & one-way funnel

**Direction:** Convert → Financial Intelligence Platform. Not the reverse.

| Surface | Funnel behaviour |
|---------|------------------|
| Marketing nav/footer | May link **into** Convert (`Solutions → Convert`) |
| Convert page (during flow) | Small links to `/` (home) and `/pricing` so visitors discover the platform before paying |
| Convert success (after pay + download) | Soft upsell to `/sign-up` only — no forced account |
| Dashboard `/upload` | **Must not** link to Convert — subscribers already have the integrated, free extract path |

Success copy:

> Want this to go straight into full statements, variance, and AI commentary?
> [Create a free Kastree account](/sign-up)

## Test plan (this session)

1. Unit/API: extract public endpoint; checkout creates `mode=payment`; download
   blocked until paid.  
2. UI: Solutions → Convert visible on marketing nav.  
3. E2E: realistic TB PDF → review → Stripe **test-mode** Checkout with
   `4242…` → download xlsx.  
4. Confirm `UploadForm` / `/trial-balances/extract-pdf` auth path unchanged.
5. Confirm Upload has no Convert outbound link; Convert success links `/sign-up`.
