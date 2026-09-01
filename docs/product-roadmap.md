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

### Medium — new work, grounded in existing data

**Sequence after Close** — Variance / Risk / Commentary / Export UI first (lower
effort, higher priority). Medium items below assume those screens exist.

- **Data visualization dashboard** — charts and graphs (trend lines, variance
  waterfalls, expense breakdowns) on top of existing statement / variance data.
- **Materiality auto-suggestion** — post-first-upload prompt suggesting
  benchmark-based thresholds from real statement figures (ISA 320-derived ranges;
  editable, never authoritative). Company creation keeps static defaults until
  then. Full target design: [`tracked-gaps.md` — Materiality thresholds](tracked-gaps.md#materiality-thresholds--static-defaults-vs-benchmark-based-suggestion).
- **Multi-period trend views** — revenue / profit progression once multiple
  trial balances exist per company.

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
- **Cash Flow Statement** — needs prior-period data (available); requires
  resolving the PPE cost / depreciation netting decision made in Statement
  Builder, since gross capex cannot be derived from a netted PPE figure today.

---

## Sequencing note

**Product 1’s “Close” items are the actual next build priority.** Medium-tier
items (data viz, materiality auto-suggestion, multi-period trends) come after
Close is shipped.

Products 2 and 3 are intentionally deferred until Product 1 has real customer
signal. **Do not begin building Product 2 or 3 items without revisiting this
document’s sequencing first.**

For granular technical debt, smaller fixes, and infrastructure gaps not captured
at product level, see [`tracked-gaps.md`](tracked-gaps.md).
