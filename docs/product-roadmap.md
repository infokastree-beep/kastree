# Kastree Product Roadmap

Two-product structure for the Kastree platform:

1. **Kastree — Financial Intelligence Platform** (Product 1) — one unified
   internal-review product. A practice uses whichever features are relevant
   (comparative statements, Variance, Commentary, Risk, Copilot, and — in
   future — reconciliation / working-paper evidence and multi-entity client
   views). Not separate, siloed products.
2. **Full Statutory Annual Report, Ireland & UK** (Product 3, renamed in
   sequencing as Product 2 below) — genuinely separate: filing-capable output
   with its own legal gate and liability posture.

The dashboard [`ProductSwitcher`](../../frontend/components/layout/ProductSwitcher.tsx)
and [`frontend/lib/products.ts`](../../frontend/lib/products.ts) were built to
support multiple product entries — add the statutory product there only when a
slice is ready to ship. Today only **FinDraft** (`id: "findraft"`) is
registered; that remains the Product 1 surface.

This is a **reference document**, not a build queue.

---

## Product 1 — Kastree — Financial Intelligence Platform (current, live)

**Status:** MVP live in production. Core loop (upload → map → validate →
statements) proven end-to-end.

**Framing:** one platform for accounting practices doing **internal review and
analysis**. Features below are add-ons of that same product — not separate
SKUs or liability regimes. Everything here stays inside the existing
“internal review only” disclaimer.

Registered in `products.ts` today as **FinDraft** (`id: "findraft"`).

### Close — shipped

Originally “same data, needs a screen.” All Close items below are live in
production.

| Feature | Status |
|---------|--------|
| **Variance Analysis** tab | Done — built and live-tested 2026-09-07 |
| **Materiality auto-suggestion** | Done — built and live-tested 2026-09-07 |
| **Risk Flags** tab | Done — built and live-tested 2026-09-07 |
| **AI Commentary** | Done — built and live-tested 2026-09-07 |
| **Business Health** summary | Done — built and live-tested 2026-09-07 |
| **Export** (Excel / PDF / CSV) | Done — built and live-tested 2026-09-07 |
| **Canonical lines expansion** | Done — built and live-tested 2026-09-07 |

### Medium — shipped

Originally “new work, grounded in existing data,” sequenced after Close. All
Medium items below are live in production.

- **Data visualization dashboard** — Done — built and live-tested 2026-09-07
  (Performance Overview charts / KPI cards / expense mix on Dashboard).
- **Multi-period trend views** — Done — built and live-tested 2026-09-07
  (period history, View period navigation, KPI drill-down). Backend
  Monthly/Quarterly/Yearly aggregation remains available; Dashboard UI toggle
  is parked until multi-quarter/year data would differentiate results (see
  [`tracked-gaps.md`](tracked-gaps.md) — Performance granularity toggle).
- **Statement line evidence drill-down** — Done — click any SOPL/SOFP/SOCIE
  face line to open source TB accounts (read-only evidence graph). Manual
  line edits, formulae, and add-line remain deferred (see
  [`tracked-gaps.md`](tracked-gaps.md)).

### Conversational statement query ("Copilot")

Done — built and live-tested 2026-09-07 (full 3-phase Copilot: Ask panel,
evidence-grounded answers, citations, Dashboard/Statements navigation).

Inspired by reviewing real reference screenshots (LucaNet's "Copilot"/"Message
Luca" chat interface). A natural-language chat panel letting a user ask
questions like "summarize expense changes this quarter" or "what changed in
gross margin over the last 2 years", answered from already-computed statement
and variance data via the existing evidence graph — NOT a new calculation
engine, a query/answer layer sitting on top of data already proven correct.

### Future Product 1 add-ons (same liability posture)

Formerly sequenced as a separate “Product 2.” Folded into Product 1 because
these features were always scoped as **SaaS productivity inside internal
review** — no liability change from the live platform. Still **not built**;
demand- and design-gated, not a commitment to build next.

- **Working Paper / Reconciliation Evidence** — attach and organize supporting
  documents (bank statements, reconciliations) against individual balance line
  items. Explicitly **not** an audit sign-off tool.
- **Client → Company multi-entity enhancements** — group-level views once
  companies exist under one client. Distinct from true accounting
  consolidation (see Product 2 — Statutory below).

---

## Product 2 — Full Statutory Annual Report, Ireland & UK (future, long-term)

Formerly “Product 3.” Kept as the **only** separate product because it is a
different **liability category**: filing-capable output. Requires its own
legal / ToS review before build, not just before launch. Not an add-on of the
internal-review Financial Intelligence platform.

**Upfront legal gate (do not start build until cleared):** counsel must confirm
whether “AI-assisted SaaS platform, not the filer/signer of record” is legally
sufficient in Ireland/UK for this use case, what disclaimer/liability structure
is actually required, and how that differs from Product 1’s settled
internal-review-only positioning (including future working-paper add-ons).
Detail in [`tracked-gaps.md`](tracked-gaps.md) — Product 3 planning notes
(section title retained for continuity; refers to this statutory product).
Framing that merely *sounds* reasonable is not enough.

- **Toggle-based note / disclosure content library** (Accurri-style pattern) —
  FRS 102 Section 1A first, matching actual target market.
- **iXBRL tagging** — distinct, later sub-phase; separate technical standard.
- **Multi-entity true consolidation** — intercompany eliminations, ownership
  %, currency translation. Explicitly excluded from current MVP scope; real
  engineering reasons documented in [`tracked-gaps.md`](tracked-gaps.md).
- **Cash Flow Statement** — *historical* statement (IAS 7 / FRS 102 style),
  not forecasting. Needs prior-period data (available); requires resolving the
  PPE cost / depreciation netting decision made in Statement Builder, since
  gross capex cannot be derived from a netted PPE figure today. Forward-looking
  cash-flow work is a separate capability — see **Future considerations** below.

---

## Future considerations (not sequenced — demand-gated)

Items below are **not** on the Product 1 Close/Medium build path and are **not**
implied by the statutory product’s historical Cash Flow Statement. Capture them
here so they are not confused with nearer work. **Do not build without real
customer demand** — the same caution already applied to ERP / direct
accounting-system integration (Xero, QuickBooks, Sage, etc.).

### Scenario analysis, cash flow forecasting, and predictive modelling

A **distinct future capability**: forward-looking what-if scenarios, cash-flow
forecasts, and predictive models on top of (or beside) proven historical
statements. Separate from the statutory product’s **Cash Flow Statement**, which
is a historical period statement derived from trial-balance / statement data.
Forecasting is a bigger, later undertaking (assumptions, drivers, model
governance, and liability surface differ from “rebuild last month’s CFS”).

### Dual-period upload for first-time comparative onboarding

**Product 1 future consideration — first-time company setup only.**

Allow a **new company’s first-ever setup** to optionally include a second,
prior-period trial balance upload so comparative statements (SOPL / SOFP /
SOCIE prior columns) — and first-run variance — can show immediately, rather
than waiting for a second real-world period to naturally occur.

This is deliberately scoped to **first-time setup only**, not a general
dual-upload option. That is the only case where no prior-period data exists
anywhere in the system yet. For every subsequent upload, a real,
already-correct prior period already exists automatically via
`find_prior_trial_balance`, so re-uploading it again would be redundant and
would introduce a real risk: two potentially different sources of the same
period’s data that could silently disagree, undermining the
single-source-of-truth design that makes the current upload flow robust.

This does **not** change or add to the core, ongoing single-file-per-period
upload flow, which remains the correct, safer default for every upload after
a company’s first.

**Distinct from** the Variance tab’s prior-period selector (and from the
Statements “View period” selector), which operate on periods already stored.
Capture only — do not build until demand is clear.

### General data export / BI connectivity

Possible future add-on: connectors or export paths for BI tools (e.g. **Power
BI**) so firms can pull Kastree statement / variance outputs into their own
reporting stacks. **Genuinely uncertain priority** — useful for some practices,
irrelevant for others. Same rule as ERP integration: wait for clear customer
demand before designing APIs, schemas, or sync jobs.

---

## Sequencing note

**Product 1 Close and Medium are complete** (including Variance, materiality,
Risk, Commentary, Business Health, Export, canonical lines, Performance
Overview / multi-period trends / KPI drill-down, statement evidence
drill-down, and full 3-phase Copilot) — built and live-tested 2026-09-07.

**Next substantial Product 1 work** is whichever polish or future add-on
(working-paper evidence, multi-entity client views) earns clear demand — still
under the same internal-review liability posture.

**The statutory annual-report product** (section above) remains the only
separate product track and **still requires its upfront legal gate** (see that
section and [`tracked-gaps.md`](tracked-gaps.md)) before any statutory-report
build starts. Future considerations above remain demand-gated.

For granular technical debt, smaller fixes, and infrastructure gaps not captured
at product level, see [`tracked-gaps.md`](tracked-gaps.md).
