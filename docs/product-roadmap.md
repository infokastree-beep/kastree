# Kastree Product Roadmap

Three-product structure for the Kastree platform. The dashboard
[`ProductSwitcher`](../../frontend/components/layout/ProductSwitcher.tsx) and
[`frontend/lib/products.ts`](../../frontend/lib/products.ts) were deliberately
built to support multiple product entries — add new products there when a slice
is ready to ship.

This is a **reference document**, not a build queue.

---

## Product 1 — Financial Intelligence (current, live)

**Status:** MVP live in production. Core loop (upload → map → validate →
statements) proven end-to-end.

Registered in `products.ts` today as **FinDraft** (`id: "findraft"`).

### Close — same data, needs a screen (build next)

Backend work for these features is largely done; the gap is frontend surfaces
on the statements dashboard.

| Feature | Backend | Frontend gap |
|---------|---------|--------------|
| **Variance Analysis** tab | Done and tested | Prior-period upload field + results table |
| **Materiality auto-suggestion** | Not built | Post-first-upload prompt suggesting benchmark-based thresholds from real statement figures. **Fast-follow alongside or immediately after Variance** — not a separate later task. Directly feeds Variance Analysis's "is this material?" flagging (Product Spec §4.3); a static generic threshold makes variance flagging inconsistently useful across companies of different sizes. Full target design: [`tracked-gaps.md`](tracked-gaps.md) (Materiality thresholds section). |
| **Risk Flags** tab | Done and tested | Display table |
| **AI Commentary** | Done and reviewed (no financial data sent to LLM) | UI for drafted text, editable, with reasoning tooltip + thumbs up/down (feedback endpoints exist) |
| **Business Health** summary | Done | Dashboard placement for the 3-bullet AI summary |
| **Export** (Excel / PDF / CSV) | Fully built and tested (incl. LibreOffice-verified currency formatting) | Dashboard export buttons |
| **Canonical lines expansion** | Not built | Six new Appendix A lines + SOFP placement (confirmed via complex TB testing). Affects mapping accuracy and statement completeness. **Fast-follow after Variance / materiality.** Full design: [`canonical-lines-expansion.md`](canonical-lines-expansion.md). |

### Medium — new work, grounded in existing data

**Sequence after Close** — including Variance UI and its materiality fast-follow.
Medium items below assume those are shipped.

- **Data visualization dashboard** — charts and graphs (trend lines, variance
  waterfalls, expense breakdowns) on top of existing statement / variance data.
- **Multi-period trend views** — revenue / profit progression once multiple
  trial balances exist per company.

### Conversational statement query ("Copilot")

Inspired by reviewing real reference screenshots (LucaNet's "Copilot"/"Message
Luca" chat interface). A natural-language chat panel letting a user ask
questions like "summarize expense changes this quarter" or "what changed in
gross margin over the last 2 years", answered from already-computed statement
and variance data via the existing evidence graph -- NOT a new calculation
engine, a query/answer layer sitting on top of data already proven correct.
Natural extension once the Commentary display and Variance tab (both already
planned, backend done) exist in the UI. Genuinely well-matched to the existing
architecture (deterministic engine + evidence graph + AI narration-only
principle already established). Sequence: after Commentary/Variance UI ships,
not before -- there's nothing to query conversationally until those exist as
real, viewable data.

---

## Product 2 — Working Paper / Audit Evidence (future)

Explicitly a **SaaS productivity tool**, not an audit sign-off tool — stays
inside the existing “internal review only” disclaimer. No liability change from
Product 1.

- **Working Paper / Reconciliation Evidence** — attach and organize supporting
  documents (bank statements, reconciliations) against individual balance line
  items.
- **Client → Company multi-entity enhancements** — group-level consolidated
  views once companies exist under one client. Distinct from true accounting
  consolidation (see Product 3).

---

## Product 3 — Full Statutory Annual Report, Ireland & UK (future, long-term)

Different **liability category** from Products 1–2 — filing-capable output.
Requires its own legal / ToS review before build, not just before launch.

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
implied by Product 3’s historical Cash Flow Statement. Capture them here so they
are not confused with nearer work. **Do not build without real customer demand**
— the same caution already applied to ERP / direct accounting-system integration
(Xero, QuickBooks, Sage, etc.).

### Scenario analysis, cash flow forecasting, and predictive modelling

A **distinct future capability**: forward-looking what-if scenarios, cash-flow
forecasts, and predictive models on top of (or beside) proven historical
statements. Separate from Product 3’s **Cash Flow Statement**, which is a
historical period statement derived from trial-balance / statement data.
Forecasting is a bigger, later undertaking (assumptions, drivers, model
governance, and liability surface differ from “rebuild last month’s CFS”).

### General data export / BI connectivity

Possible future add-on: connectors or export paths for BI tools (e.g. **Power
BI**) so firms can pull Kastree statement / variance outputs into their own
reporting stacks. **Genuinely uncertain priority** — useful for some practices,
irrelevant for others. Same rule as ERP integration: wait for clear customer
demand before designing APIs, schemas, or sync jobs.

---

## Sequencing note

**Product 1’s “Close” items are the actual next build priority**, with
materiality auto-suggestion a **fast-follow to Variance** (not Medium-tier later
work) and **canonical lines expansion** fast-follow after those (see
[`canonical-lines-expansion.md`](canonical-lines-expansion.md)). Remaining
Medium items (data viz, multi-period trends) come after Close is shipped.

Products 2 and 3 are intentionally deferred until Product 1 has real customer
signal. **Do not begin building Product 2 or 3 items without revisiting this
document’s sequencing first.** Future considerations above are likewise
deferred until demand is concrete.

For granular technical debt, smaller fixes, and infrastructure gaps not captured
at product level, see [`tracked-gaps.md`](tracked-gaps.md).
