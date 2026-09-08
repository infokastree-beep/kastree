# Kastree Product Roadmap

Two-product structure for the Kastree platform:

1. **Kastree — Financial Intelligence Platform** (Product 1) — one unified
   internal-review product. A practice uses whichever features are relevant
   (comparative statements, Variance, Commentary, Risk, Copilot, and — in
   future — reconciliation / working-paper evidence and multi-entity client
   views). Not separate, siloed products.
2. **Full Statutory Annual Report, Ireland & UK** (Product 2; formerly
   Product 3) — genuinely separate: filing-capable output with its own legal
   gate and liability posture.

Former working-paper / multi-entity work (old Product 2) is **folded into
Product 1** as future add-ons. Those items already carried **no liability
change** from Product 1 — a structural simplification, not a new liability
decision.

The dashboard [`ProductSwitcher`](../../frontend/components/layout/ProductSwitcher.tsx)
and [`frontend/lib/products.ts`](../../frontend/lib/products.ts) were built to
support multiple product entries — add the statutory product there only when a
slice is ready to ship. Today only **FinDraft** (`id: "findraft"`) is
registered; that remains the Product 1 surface.

This is a **reference document**, not a build queue. **Nothing below the
shipped Product 1 surface is scheduled for build** until real customer usage
of Product 1 shows genuine demand (and, for Product 2, until the legal gate
clears).

---

## Product 1 — Kastree — Financial Intelligence Platform (current, live)

**Status: complete and ready to sell now.**

MVP is live in production. Core loop (upload → map → validate → statements →
Variance / Risk / Commentary / Copilot / Export / Dashboard) is proven
end-to-end and live-tested. **Paywall is live:** public `/pricing`, free=3 /
starter=10 / Growth=30 / Practice=75 client caps enforced on create, Stripe
Checkout + webhook proven with a real test-mode payment (2026-09-07). Product 1
is a **finished sellable surface** — not a half-built platform waiting on the
items in this document.

**Framing:** one platform for accounting practices doing **internal review and
analysis**. A practice uses the features that matter for the engagement —
comparative statements, Variance, Commentary, Risk, Copilot, and (later)
reconciliation / working-paper evidence — rather than jumping between separate
products. Everything here stays inside the existing “internal review only”
disclaimer.

Registered in `products.ts` today as **FinDraft** (`id: "findraft"`).

### Close — shipped

| Feature | Status |
|---------|--------|
| **Variance Analysis** tab | Done — built and live-tested 2026-09-07 |
| **Materiality auto-suggestion** | Done — built and live-tested 2026-09-07 |
| **Risk Flags** tab | Done — built and live-tested 2026-09-07 |
| **AI Commentary** | Done — built and live-tested 2026-09-07 |
| **Business Health** summary | Done — built and live-tested 2026-09-07 |
| **Export** (Excel / PDF / CSV) | Done — built and live-tested 2026-09-07 |
| **Canonical lines expansion** | Done — built and live-tested 2026-09-07 |
| **Paywall (pricing + Checkout)** | Done — `/pricing` live; client-limit enforcement live; Stripe Checkout + webhook proven with real test payment 2026-09-07 (`free` → `starter`) |

### Medium — shipped

- **Data visualization dashboard** — Done — built and live-tested 2026-09-07
  (Performance Overview charts / KPI cards / expense mix on Dashboard).
- **Multi-period trend views** — Done — built and live-tested 2026-09-07
  (period history, View period navigation, KPI drill-down).
- **Statement line evidence drill-down** — Done — click any SOPL/SOFP/SOCIE
  face line to open source TB accounts (read-only evidence graph). Manual
  line edits, formulae, and add-line remain deliberately unbuilt (see
  [`tracked-gaps.md`](tracked-gaps.md)).

### Conversational statement query ("Copilot") — shipped

Done — built and live-tested 2026-09-07 (full 3-phase Copilot: Ask panel,
evidence-grounded answers, citations, Dashboard/Statements navigation).

Natural-language questions answered from already-computed statement and
variance data via the existing evidence graph — **not** a new calculation
engine.

---

## Future directions (captured, not scheduled)

**None of the items in this section are scheduled for immediate build.** They
are a complete record of directions already discussed. Build only when real
Product 1 customer usage indicates genuine demand (Product 2 also requires its
legal gate).

### 1. Working Paper / Reconciliation Evidence — first in line when demand appears

**Product 1 add-on** (same internal-review liability posture). Formerly a
standalone “Product 2”; folded in because it never changed liability.

Attach supporting documents (bank statements, reconciliations) against
statement line items, **reusing the existing drill-down /
`source_account_ids` evidence pattern as the anchor point**. Real, contained
scope — explicitly **not** an audit sign-off tool.

**Sequencing:** first in line whenever Product 1 has real customer signal and
appetite for more building. Still demand-gated — not a commitment to build
next on a calendar.

Also under this Product 1 add-on umbrella (same posture, still unbuilt):

- **Client → Company multi-entity enhancements** — group-level views once
  companies exist under one client. Distinct from true accounting
  consolidation (see Product 2 below).

### 2. Product 2 — Full Statutory Annual Report, Ireland & UK

Genuinely **separate** product (formerly Product 3). Different **liability
category**: filing-capable output. **Paused** behind the specific legal
consultation already documented in [`tracked-gaps.md`](tracked-gaps.md)
(Product 2 — statutory reports — planning notes).

**Upfront legal gate (do not start build until cleared):** counsel must confirm
whether “AI-assisted SaaS platform, not the filer/signer of record” is legally
sufficient in Ireland/UK for this use case, what disclaimer/liability structure
is actually required, and how that differs from Product 1’s settled
internal-review-only positioning. Framing that merely *sounds* reasonable is
**not** enough.

Scoped capabilities (after the gate clears — still not scheduled):

- **Toggle-based note / disclosure content library** (Accurri-style) — FRS 102
  Section 1A first.
- **iXBRL tagging** — later sub-phase; separate technical standard.
- **Multi-entity true consolidation** — intercompany eliminations, ownership
  %, currency translation (explicitly out of Product 1).
- **Cash Flow Statement** — *historical* (IAS 7 / FRS 102 style), not
  forecasting. Needs prior-period data; requires resolving PPE cost /
  depreciation netting so gross capex is derivable. Forward-looking cash-flow
  work is a separate initiative (section 3 below).

### 3. Internal-use-only scenario analysis / forecasting / budgeting

A **large architectural undertaking**, correctly deferred. Scope includes
what-if scenarios, cash-flow forecasts, predictive modelling, and budgeting on
top of (or beside) proven historical statements.

**Hard design constraint:** the system must safely distinguish **real uploaded
data** from **hypothetical user input** everywhere (statements, variance,
exports, Copilot, drill-down). That boundary is the cost of the initiative —
do not start casually.

**Liability:** no new external-filing concern while scoped **internal-use
only** (same Product 1 disclaimer family). Still a major Product 1-adjacent
initiative, not a polish item. Separate from Product 2’s historical Cash Flow
Statement.

### 4. Smaller items (demand-gated polish / data prerequisites)

| Item | Notes |
|------|--------|
| **Member invites** | Org member invite-by-email flow — useful for multi-user practices; not required to sell Product 1 solo. |
| **Monthly / Quarterly / Yearly toggle** | **Already built** on the performance-overview API; **hidden in UI** until real multi-quarter / multi-year company data would differentiate results (see [`tracked-gaps.md`](tracked-gaps.md) — Performance granularity toggle). Unhide when data warrants — not a new build. |
| **Departmental drill-down** | Needs **new data collection** first (department / cost-centre dimensions on TB or mapping). Cannot ship as a pure UI add-on. |
| **BI / Power BI connectivity** | Export or connector paths into firm BI stacks. Genuinely uncertain priority — wait for clear demand. |
| **Dual-period upload for new companies** | **First-time company setup only** — optional second (prior) TB so comparative columns and first-run variance appear immediately. Not a general dual-upload; later periods keep the single-file-per-period flow via `find_prior_trial_balance`. Distinct from Variance / “View period” selectors on already-stored periods. |

Same rule for all rows: **do not build (or unhide) until Product 1 usage shows the need.**

### 5. Future considerations (external research — demand-gated)

Consolidated directions from external product/research input. **All genuinely
promising. All correctly demand-gated.** Same discipline as the rest of this
roadmap: capture the idea so it is not lost; **do not build without real
customer signal** from Product 1 usage. None of these are on a build schedule.

| Direction | Why it is promising | Gate / constraint |
|-----------|---------------------|-------------------|
| **AI Review Assistant** | Expand today’s deterministic Risk flags (and related Variance / Commentary surfaces) into a genuine *“why did this change?”* explainer for the accountant — narrative grounded in evidence already on the period, not a second calculation engine. Natural extension of Copilot + Risk + Commentary, still under Golden Rule (Python does the math; LLM does the narrative; no raw amounts in prompts). | Demand that Risk/Variance alone is not enough for review conversations; keep fail-soft if LLM is down. |
| **Firm-wide mapping intelligence** | Learn mapping patterns across a practice’s clients (with strict org isolation) so new companies inherit better Tier 1–4 suggestions. Biggest lever for cutting manual mapping time once Tier 4 is proven with a real key. | Only after real multi-client volume; never cross-org leakage; no training on customer data without explicit contractual opt-in (see privacy / DPA posture). |
| **Client meeting pack generation** | One-click pack for a client meeting: statements, variance highlights, risk flags, business-health bullets, optional Ask excerpts — exportable PDF/Deck-style pack. Reuses existing evidence; packaging, not new math. | Clear request from practices that already run Product 1 end-to-end before meetings. |
| **Management accounts packs** | Recurring monthly/quarterly management-accounts bundle (formatted SOPL/SOFP/SOCIE + commentary + KPIs) aimed at fractional CFOs / practice MA workflows. Distinct from Product 2 statutory filing output. | Demand for recurring MA delivery; stay internal-review framing — not filing-capable. |
| **Industry benchmarking** | Compare a company’s ratios/trends to anonymised peer cohorts (sector, size). High client value; hard data and privacy requirements. | Meaningful cohort size + anonymisation design; no fake benchmarks from thin data. |
| **AI tax-review prompts (not advice)** | Prompted checklists / questions that help an accountant *review* tax-sensitive lines (e.g. unusual tax account movements) using period evidence — explicitly **not** tax advice, computation, or filing. | Counsel-ready disclaimer; never compute tax or recommend elections; Product 1 internal-review posture only. |
| **Practice operating system (longer-term vision)** | Broader practice workflow layer: filing deadlines, task management, client portal — Kastree as the operating hub around financial intelligence rather than a single TB→statements tool. | Only after Product 1 is deeply embedded; large scope; treat as a multi-year vision, not a feature ticket. Client portal and deadline tooling have their own auth, liability, and ops costs. |

**Explicit non-goals until demand proves otherwise:** do not start any row above
as speculative platform work, do not dilute Product 1 sellability chasing them,
and do not blur Product 2’s statutory legal gate into these Product 1–adjacent
ideas.

---

## Sequencing note

| Track | State |
|-------|--------|
| **Product 1 (sellable)** | **Complete and ready to sell now.** Close, Medium, Copilot, evidence drill-down, **paywall** (pricing + tier limits + Stripe Checkout/webhook) — live-tested 2026-09-07. |
| **Working Paper / Reconciliation Evidence** | First Product 1 build candidate **when** real customer signal appears. Contained scope on existing evidence anchors. |
| **Product 2 (Statutory)** | Paused — legal consultation gate in [`tracked-gaps.md`](tracked-gaps.md). Only separate product. |
| **Scenario / forecast / budget** | Captured; large architecture; internal-only; not casual. |
| **Smaller items** | Captured in the table above; demand-gated. |
| **Future considerations (research)** | Captured in §5; promising directions only — **no build without customer signal**. |

**Nothing in “Future directions” is on an immediate build schedule.** Sell and
learn from Product 1 first.

For granular technical debt, smaller fixes, and infrastructure gaps not captured
at product level, see [`tracked-gaps.md`](tracked-gaps.md).
