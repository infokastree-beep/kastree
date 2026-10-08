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

### Sole trader and farm accounts — a Product 1 segment (positioning only)

**Status: confirmed 2 October 2026. Positioning only. The reporting
framework is simpler than FRS 102. The tax judgment is not.**

A distinct customer segment, separate from Product 2. Local practices often
carry a high volume of sole-trader and farm clients whose year-end work is
Form 11-driven: a simple profit-and-loss summary, prepared so the accountant
can complete the client's income-tax return.

**Confirmed for Irish sole traders, including a farm carried on as a sole
trade.** There is no mandatory financial-reporting framework. FRS 102
(including Section 1A) and FRS 105 do not apply. Those standards apply to
companies and to the other entities in their scope. A sole trader's accounts
exist to support the Form 11 income-tax return. Presentation is flexible:
nothing in those standards prescribes the face of the statements. Revenue
still expects records that support the return. That is a tax record-keeping
duty, not a requirement to follow FRS 102 or FRS 105. A farm or other client
that is a limited company stays on the Product 2 side of this line.

The reporting framework is genuinely simpler than FRS 102. There is no
statutory sub-category and no disclosure note. That is not a claim that the
compliance work is done. Real accounting judgment is still required before
any figure is ready for Form 11:

- Capital versus revenue. An improvement is not a repair, and a fixed-asset
  addition is not an expense.
- Drawings stay out of expenses. That includes the owner's wages and private
  costs paid through the business.
- Depreciation in the accounts is not the capital-allowance deduction on
  the return.
- VAT has to be treated consistently. A mix of VAT-inclusive and
  VAT-exclusive amounts is not a finished extract.

Product 1's live loop is the internal review a practice can use today:

- Trial balance upload (Excel / CSV, and the existing GL-to-TB path where a
  practice starts from a ledger).
- AI-assisted mapping suggestions, confirmed by the accountant.
- Variance commentary against a prior period, where one exists.

Those engagements do not need an FRS 102 face or the continuation
translator. They also do not perform the four checks above. The open
Product 2 question — which canonical line has a single statutory home —
does not apply to this segment. The tax judgment still does.

The book is high-volume, and tools built around company statutory packs are
a poor fit for the reporting framework. That is the positioning. It is not
a finished Form 11 product.

Messaging stays inside the existing Product 1 posture. Kastree does not
prepare or file Form 11, and it does not produce a statutory annual report
for this segment. The practice remains the reviewer and the filer.

#### Form 11 Summary — considered, not built

**Status: design recorded 2 October 2026. No code.** The line-by-line rules
are in [`form11-summary-rules.md`](form11-summary-rules.md), pinned to Form
11 2025 (tax year 2025), lines 124–168, as described in Revenue's *Guide to
Completing 2025 Pay and File Tax Returns*. A later year's form is a new
line map.

Confirmed structure of the Extracts from Accounts. The panel is extracts
from the accounts. Revenue says it is not a tax-adjustment computation.
The accounts-extract boxes are a small fixed set:

| Lines | What Revenue asks for |
| --- | --- |
| 124–125 | Accounts period, from and to |
| 128 | Sales / Receipts / Turnover, excluding Government payments |
| 129 | Receipts from Government Agencies (GMS, Department of Agriculture payments, and the like) |
| 130 | Other trading income, including tax-exempt trading income. Not rental, dividends, or interest |
| 131–132 | Purchases, then gross trading profit |
| 133–144 | Expenses: wages, additional staff costs, RCT subcontractors, other subcontractors, professional fees, motor travel and subsistence as one box, repairs, rental expenses, depreciation and goodwill write-off, bad-debt provisions, then **Other Expenses** (143) for every other profit-and-loss expense, and 144 for expense credits |
| 145–156 | Capital and balance-sheet extracts: capital introduced, drawings, closing capital, stock, debtors, cash, borrowings, creditors, tax creditors, net assets |
| 157–158 | Net trade profit, or loss, per the accounts |
| 159–168 | Adjusted-profit add-backs and deductions. Not an extract from the trial balance |

Motor and travelling are not separate extract boxes. Line 138 is "Motor,
Travel and Subsistence", and the guide says to add those accounts together.
Line 160, "Motor Expenses", is the private-use add-back in the tax
computation. "Other Expenses" (143) is Revenue's own residual: every other
profit-and-loss expense that is not one of the named boxes.

The reporting boxes are a smaller set than FRS 102 Section 1A. There are no
disclosure notes and no fixed-asset class split. Line 143 is Revenue's
residual reporting box for a profit-and-loss expense that has no named box.
It is not a decision that the amount is revenue rather than capital,
allowable, or VAT-consistent.

The feature, when it is built, is a second choice on the existing Reporting
framework dropdown beside "FRS 102 Section 1A (Ireland)": **Sole Trader /
Form 11 Summary**. It uses the trial balance and the confirmed Product 1
mappings already on the page. It does not upload a new file and it does not
ask for a new mapping pass. It does not generate a statutory pack. It lists
each Revenue box, the amount, and the accounts behind it, so the accountant
can key the figures into ROS. Lines 159–168 are left blank. Kastree still
does not file the return.

This is worth consideration as a smaller build than the statutory
translation. It does not replace the four checks above. The summary has to
handle them, or flag each one for the accountant. It must not assume them
away. The rules in the design note are for review before any code.

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

**Pre-client-use gate:** qualified reviewer sign-off of statutory wording, and
a customer-facing DPA (GDPR Article 28) drafted, reviewed, and published. Both
are human legal artifacts. They gate real client use. Detail is in
[`tracked-gaps.md`](tracked-gaps.md). The OpenAI DPA remains the v1.1
precondition already in the v7.6 specification and is not a current blocker.

**Real, significant gap — pre-2026 periods (near-term once beta starts, not a
someday item):** The only built pack, `frs102-1a-ie` `2024.09`, supports
periods beginning on or after 1 January 2026. The previous FRS 102 Section 1A
standard (pre-Periodic-Review-2024) has not been built as a separate pack. A
2025 or earlier year-end, or a 2025/2026 year that has not elected early
adoption, cannot use Product 2 at all. That is likely to block the first real
client, because most companies will not yet have a clean 2026-01-01-onward
year. Building that earlier pack, or an early-adoption toggle (FRC guidance
permits early application if the amendments are applied in full), is a
near-term priority when real beta testing begins. Detail in
[`tracked-gaps.md`](tracked-gaps.md) (Product 2 — pre-2026 FRS 102 Section 1A).

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

#### Complete the intake cycle (Intake Completion Initiative)

Product 1’s proven engine starts at a **trial balance**:

**GL (Excel or PDF) → Trial Balance → [existing engine: mapping → statements →
variance → commentary → dashboard]**

Today only a clean **xlsx/csv TB** can enter that pipeline. Completing the
intake cycle means a practice can start from **whatever raw data they actually
have** — clean TB, PDF TB, GL export, or PDF GL — and always reach the same
trusted path. That is one coherent expansion of the core promise, **not** a set
of disconnected features. Treat as a single **Intake Completion Initiative**
(also called “complete the intake cycle”), already detailed in the companion
**technical MVP spec** and **business proposal** (external to this roadmap).

##### Customer signal (2026-09-08) — demand validated

**Real prospect request:** a prospect specifically asked for **PDF trial
balance** and **general ledger** support. That elevates this initiative from
speculative research to **validated demand**.

**Phase 1 (PDF trial balance extraction) = DONE** — built, tested (clean,
messy, and OCR-fallback paths), and safety-proven (mandatory review step
confirmed unbypassable via API and UI). Commit `d01f513` on origin + github;
production frontend SHA verified.

**Phase 3 (GL → TB conversion) — demand separately confirmed (2026-09-09).**
Client (own words): GL dump in PDF or Excel → Excel + trial balance, quickly.
Design draft (period cutoffs + opening-balance modes A/B/C, debit=credit gate,
review-before-pipeline; free in-flow only): [`gl-to-tb-design.md`](gl-to-tb-design.md).
**No implementation until design approval.** Standalone Convert remains TB-only.

##### Phase status

| Phase | Scope | Status |
|-------|--------|--------|
| **Phase 1** | **PDF trial balance extraction only** | **DONE** — built, tested (clean / messy / OCR-fallback), safety-proven (review unbypassable via API + UI). Upload selector → `pdfplumber` + OCR → review table → CSV into existing upload/mapping pipeline. |
| **Phase 3** | **GL → TB conversion** (Excel and PDF GL) | **BUILT (2026-09-09)** — Modes A/B/C, debit=credit hard fail, review-before-pipeline. Free in-flow Upload (`POST /trial-balances/convert-gl`). Design: [`gl-to-tb-design.md`](gl-to-tb-design.md). Convert stays TB-only. |

(Phase numbering matches the companion specs; intermediate phases there, if any,
are unchanged by this note.)

**Mapping is not a standalone add-on.** Account mapping is **core subscription
value** — part of the Product 1 loop, not sellable alone as an intake upsell.

**Eventual hybrid monetization — updated 2026-09-09:**

1. **In-flow (subscribers)** — Upload-path integration (PDF-TB extract → review →
   existing pipeline; GL→TB when Phase 3 is in production). Stays as-is for
   subscribers.
2. **Standalone Convert (public Solutions product)** — **REMOVED (2026-09-09).**
   `/solutions/convert`, Solutions nav, and one-time Checkout are gone from the
   public site. See [`solutions-convert-design.md`](solutions-convert-design.md).
   Do not reintroduce without an explicit product decision.

**Do not** collapse PDF tools and GL tools into unrelated tickets. Phase 3
in-flow build is specified in [`gl-to-tb-design.md`](gl-to-tb-design.md).

Related rows below stay demand-gated individually.

| Direction | Why it is promising | Gate / constraint |
|-----------|---------------------|-------------------|
| **PDF trial balance extraction (AI-assisted OCR/parsing) — Phase 1** | Practices whose only TB export is PDF **cannot use Kastree at all** today (xlsx/csv only). AI-assisted OCR/parsing into the **existing** parse → map pipeline opens that funnel without a second product surface. **Validated by real prospect ask (2026-09-08).** Smallest useful slice of the Intake Completion Initiative. | **DONE** — built, tested (clean / messy / OCR-fallback), safety-proven (mandatory review unbypassable via API + UI). Golden Rule: extraction → structured TB rows for deterministic Python math; LLM not used for amounts; fail closed on low confidence. |
| **General Ledger → Trial Balance (Excel and PDF GL) — Phase 3** | Completes the intake cycle: raw ledger → TB → existing mapping/statements engine. Core mechanic: sum transactions by GL code into account totals. | **BUILT (in-flow, 2026-09-09)** — Modes A/B/C, hard debit=credit gate, review-before-pipeline. Free for subscribers inside Upload. Public Convert product removed. Design: [`gl-to-tb-design.md`](gl-to-tb-design.md). |
| **General PDF→Excel for accounting documents** | User picks document type (trial balance, fixed asset register, AP statement, AR statement, GL, …); AI extracts and structures into Excel. Well-targeted at the **real accountant workflow** (not a generic PDF tool). Directly extends PDF-TB extraction to documents practices regularly convert manually — including GL PDFs as an extraction front-end to GL→TB. Real multi-document-type parsing is **meaningfully bigger** than single-format PDF-TB alone; prioritize highly **if** validated. | Confirm frequency of manual PDF→Excel conversion in early customer talks (which document types, how often). Prefer typed extractors over one opaque “convert anything”; fail closed on low confidence; never invent figures. TB path should still feed the existing mapping pipeline; GL path should feed GL→TB (not invent statement math). Other types may stop at downloadable Excel until a clear Product 1 hook exists. Scope and QA cost scale with each document type — ship TB first if funnel-blocked, then expand. |
| **Bank statement → categorised transactions (upstream intake)** | Separate intake path: bank statements in → categorised transactions, with a natural **upsell into existing TB mapping** / review. Upstream of the current trial-balance loop — expands who arrives at Product 1 rather than only deepening it. Distinct from GL→TB (bank lines ≠ full GL). | Demand that bank-PDF / CSV statement workflows are how prospects work today. Treat as a **distinct pipeline** (not a silent TB substitute); categorisation ≠ TB integrity; keep org isolation and no cross-client training without opt-in. Upsell into mapping must stay optional and explicit. |
| **AI Review Assistant** | Expand today’s deterministic Risk flags (and related Variance / Commentary surfaces) into a genuine *“why did this change?”* explainer for the accountant — narrative grounded in evidence already on the period, not a second calculation engine. Natural extension of Copilot + Risk + Commentary, still under Golden Rule (Python does the math; LLM does the narrative; no raw amounts in prompts). | Demand that Risk/Variance alone is not enough for review conversations; keep fail-soft if LLM is down. |
| **Firm-wide mapping intelligence** | Learn mapping patterns across a practice’s clients (with strict org isolation) so new companies inherit better Tier 1–4 suggestions. Biggest lever for cutting manual mapping time once Tier 4 is proven with a real key. | Only after real multi-client volume; never cross-org leakage; no training on customer data without explicit contractual opt-in (see privacy / DPA posture). |
| **Client meeting pack generation** | One-click pack for a client meeting: statements, variance highlights, risk flags, business-health bullets, optional Ask excerpts — exportable PDF/Deck-style pack. Reuses existing evidence; packaging, not new math. | Clear request from practices that already run Product 1 end-to-end before meetings. |
| **Management accounts packs** | Recurring monthly/quarterly management-accounts bundle (formatted SOPL/SOFP/SOCIE + commentary + KPIs) aimed at fractional CFOs / practice MA workflows. Distinct from Product 2 statutory filing output. | Demand for recurring MA delivery; stay internal-review framing — not filing-capable. |
| **Industry benchmarking** | Compare a company’s ratios/trends to anonymised peer cohorts (sector, size). High client value; hard data and privacy requirements. | Meaningful cohort size + anonymisation design; no fake benchmarks from thin data. |
| **AI tax-review prompts (not advice)** | Prompted checklists / questions that help an accountant *review* tax-sensitive lines (e.g. unusual tax account movements) using period evidence — explicitly **not** tax advice, computation, or filing. | Counsel-ready disclaimer; never compute tax or recommend elections; Product 1 internal-review posture only. |
| **Compliance deadline calendar + live Google Calendar sync** | Encode **standard, publicly known** filing-deadline rules per jurisdiction (Irish Revenue / CRO first) as fixed formulas — **not** client-specific legal research. Deliver a **live, subscribable `.ics` feed per organisation** (Google Calendar re-syncs subscribed feeds). Contained early wedge of the “practice OS” vision. **Parked 2026-09-08** after a full IE rule × company-data audit (see subsection below) — almost no company-specific deadlines are derivable from today’s schema without new optional fields; do not guess. | **Still demand-gated:** resume only when real customers need this gap closed. Never present as personalised tax/legal advice; token-protect the feed URL; reminders ≠ filing (Product 2 liability stays out). |
| **Practice operating system (longer-term vision)** | Broader practice workflow layer: filing deadlines, task management, client portal — Kastree as the operating hub around financial intelligence rather than a single TB→statements tool. | Only after Product 1 is deeply embedded; large scope; treat as a multi-year vision, not a feature ticket. Client portal and deadline tooling have their own auth, liability, and ops costs. The compliance `.ics` feed above is the preferred first wedge **if** demand appears — not a licence to build the full OS. |

#### Compliance calendar — IE rule × data-field audit (parked 2026-09-08)

Diagnosis against the live `companies` model at park time (name, currency,
company_number, industry, company_type, materiality only — **no** incorporation,
ARD, year-end, VAT/PAYE schedules, CT size, or opt-in flags).

**Company fields already present that help:** none for deadline math. Existing
identity fields do not unlock any IE filing date. Resume work must add optional
nullable compliance fields and **never guess** unset schedules.

**New company fields that would be required to schedule (all optional /
nullable; unset = rule blocked, not invented):**

| Field | Purpose |
|-------|---------|
| `incorporation_date` | CRO first Annual Return (B1) |
| `annual_return_date` (ARD) | CRO subsequent B1 (ARD + 56 days) |
| `accounting_year_end_month` / `accounting_year_end_day` | CT prelim, CT1, Form 8-2, iXBRL |
| `vat_filing_frequency` (`monthly` / `bi_monthly` / `quarterly` / `none`) | VAT 3 + RTD |
| `vat_bimonth_end_even` | Bi-monthly VAT period alignment |
| `paye_filing_frequency` (`monthly` / `quarterly` / `none`) | PAYE/PRSI/USC/LPT + DWT; RCT quarterly vs monthly |
| `ct_size_class` (`small` / `large`) | Large vs small CT preliminary tax rules |
| `rct_applicable` (bool, default false) | RCT monthly/quarterly — opt-in only |
| `oss_ioss_applicable` (bool, default false) | OSS/IOSS — opt-in only |
| `form11_relevant` (bool, default false) | Director/individual Form 11 / CGT / CAT track |
| `compliance_jurisdiction` (e.g. `IE`) | Gate Irish rules; do not assume |

**Org field for live feed:** `compliance_calendar_token` (rotatable secret) for
`GET …/compliance/calendar.ics?org_id=…&token=…` (subscribe URL; no Clerk cookie).

**Rule matrix (Irish rules from the product brief):**

| Rule | Buildable now? | Status | Required data |
|------|----------------|--------|---------------|
| PAYE/PRSI/USC/LPT monthly (14th; ROS 23rd) + DWT | No | **Blocked** | `paye_filing_frequency=monthly` |
| PAYE quarterly (14th/23rd) small employers | No | **Blocked** | `paye_filing_frequency=quarterly` |
| VAT 3 monthly (19th) + RTD when period ends | No | **Blocked** | `vat_filing_frequency=monthly` |
| VAT 3 bi-monthly / quarterly (19th; ROS often 23rd) | No | **Blocked** | `vat_filing_frequency` (+ `vat_bimonth_end_even` for bi-monthly) |
| RCT monthly (23rd) / quarterly | No | **Blocked** | `rct_applicable=true` (+ quarterly PAYE for RCT quarterly) |
| OSS/IOSS (last day of month after quarter) | No | **Blocked** | `oss_ioss_applicable=true` (rare for ICP) |
| CT prelim 1 (large) — 23rd of 6th month of AP | No | **Blocked** | year-end + `ct_size_class=large` |
| CT prelim 2 / small single instalment — 23rd of 11th month of AP | No | **Blocked** | year-end + `ct_size_class` |
| CT1 + balancing payment — 23rd of 9th month after YE | No | **Blocked** | year-end month/day |
| Form 8-2 — last day of 9th month after YE | No | **Blocked** | year-end month/day |
| iXBRL — 3 months after CT1 due | No | **Blocked** | year-end month/day |
| CRO first B1 — 6 months from incorporation | No | **Blocked** | `incorporation_date` |
| CRO subsequent B1 — within 56 days of ARD | No | **Blocked** | `annual_return_date` |
| Form 11 / CGT return / CAT IT38 (31 Oct; ROS mid-Nov) | No | **Blocked** | `form11_relevant=true` |
| CGT payment 15 Dec (Jan–Nov) / 31 Jan (Dec disposals) | No | **Blocked** | `form11_relevant=true` |
| Pillar Two (MNE >€750m) | n/a | **Out of scope** | Not for Kastree ICP — flag only, do not build |

**Intended slice when resumed (not built):** pure-Python IE rule engine
(emit `scheduled` only when required fields present; otherwise
`blocked_missing_data`); JSON deadlines API + tokenised live `.ics` per org;
Compliance Calendar section on Clients page (upcoming + missing-data panel +
subscribe URL); optional compliance fields on company create/edit. No
implementation was shipped — design only.

**Explicit non-goals until demand proves otherwise:** do not start any row above
as speculative platform work, do not dilute Product 1 sellability chasing them,
and do not blur Product 2’s statutory legal gate into these Product 1–adjacent
ideas.

### 6. Long-term — transaction-level GL risk / fraud analytics (NOT intake; NOT next)

**Status:** captured as a **distinct, long-term future consideration only**.
**Not** scheduled. **Not** a natural follow-on to demand-validated GL→TB
intake ([§5 Phase 3](#phase-status)). Do not fold this into Upload, Convert,
or “messy GL” hardening work.

**What it would be (if ever pursued):** genuine **audit / forensic-accounting**
capability over transaction-level general-ledger data — for example:

- Timing anomalies (weekend / period-end / unusual-hour posting patterns)
- Benford’s Law digit analysis
- Duplicate / near-duplicate transaction detection
- Keyword screening on narratives
- Statistical outliers on amount / velocity / account pairs
- ML risk scoring across those signals

That is a **real, substantial, specialized** product surface — analysis of
*transactions for risk and fraud indicators* — not “another mode” of GL→TB
conversion (which only buckets movements into a closing trial balance for the
existing Product 1 engine).

**Why it is separated from GL→TB:**

| GL → TB (intake, §5 Phase 3) | Transaction-level risk / fraud analytics (this §) |
|------------------------------|---------------------------------------------------|
| Demand-validated conversion into a TB | Forensic / audit-style investigation tooling |
| Deterministic bucketing + balance gate | Statistical / ML judgement over raw lines |
| Feeds Product 1 internal-review statements | Implies assurance / fraud-detection posture |
| Free in-flow Upload for subscribers | Would be its own capability (and liability) |

**Liability boundary (same care held all session):** Kastree is explicitly
positioned as **not an audit tool**. Shipping fraud / forensic analytics
crosses that boundary — same class of risk already protected for Product 2
(statutory) and for any “assurance-sounding” Product 1 language. Treating
this as a polish item on GL intake would be a category error.

**Hard gate before any design work:** **dedicated legal review** of its own
(not reused Product 1 disclaimers, not the Product 2 filing gate by
analogy). Counsel must address whether — and under what framing,
disclaimers, and liability structure — a SaaS product may offer
transaction-level risk / fraud analytics to accounting practices without
being held out as an audit or forensic tool. **No wireframes, schemas, or
spikes until that review exists.**

**Sequencing:** correctly placed **well behind** (1) Product 1 sell-and-learn
validation with real customers, and (2) even Product 2 (statutory reports)
after its own legal gate. Do not pull forward because GL files are now in
the product.

### 7. Long-term — embeddable mapping and statement API (NOT near-term)

**Status:** captured as a long-term infrastructure direction only. **Not**
scheduled. **Not** a Product 2 feature and **not** a near-term priority.

**What it would be (if ever pursued):** other software calling Kastree's
mapping and statement engine the way practices call Plaid, Codat, or Railz —
an API that accepts a trial balance and returns deterministic mapped lines
and statements. Python would still own every figure. The caller would not
get an LLM that calculates.

**Why it waits.** This only makes sense after the current product has real
customers and real product-market fit. Building an embeddable API before
that would split effort away from the core workflow practices actually use.
No public API, no partner sandbox, and no extra auth model until that fit
is proven.

---

## Sequencing note

| Track | State |
|-------|--------|
| **Product 1 (sellable)** | **Complete and ready to sell now.** Close, Medium, Copilot, evidence drill-down, **paywall** (pricing + tier limits + Stripe Checkout/webhook) — live-tested 2026-09-07. |
| **Sole trader / farm accounts** | **Positioning only.** Confirmed 2 October 2026: an Irish sole trader (including a sole-trader farm) has no mandatory reporting framework — not FRS 102, not FRS 105. The reporting framework is simpler than FRS 102. Capital versus revenue, drawings, capital allowances, and VAT consistency are still real checks. A limited company stays with Product 2. |
| **Form 11 Summary** | **Design only, not built.** A second Reporting-framework choice beside FRS 102 Section 1A. Maps the confirmed trial balance onto Form 11 2025 extracts (lines 124–168). Other Expenses is a residual reporting box, not a substitute for those checks. The summary must flag them for review. Rules in [`form11-summary-rules.md`](form11-summary-rules.md). |
| **Working Paper / Reconciliation Evidence** | First Product 1 build candidate **when** real customer signal appears. Contained scope on existing evidence anchors. |
| **Product 2 (Statutory)** | Paused — legal consultation gate in [`tracked-gaps.md`](tracked-gaps.md). Only separate product. |
| **Scenario / forecast / budget** | Captured; large architecture; internal-only; not casual. |
| **Smaller items** | Captured in the table above; demand-gated. |
| **Future considerations (research)** | Captured in §5. **Intake Completion Initiative:** prospect-validated (2026-09-08); **Phase 1 PDF-TB = DONE** (built, tested clean/messy/OCR, review gate safety-proven); **Phase 3 GL→TB** built in-flow (2026-09-09) — conversion only, not analytics. |
| **GL risk / fraud analytics (§6)** | **Long-term only.** Distinct from GL→TB. Forensic/audit territory; **dedicated legal review before any design.** Behind Product 1 validation and Product 2. |
| **Embeddable mapping / statement API (§7)** | **Long-term only.** Infrastructure play after real customers and product-market fit. Not near-term. |

**Nothing in “Future directions” is on an immediate build schedule.** Sell and
learn from Product 1 first.

For granular technical debt, smaller fixes, and infrastructure gaps not captured
at product level, see [`tracked-gaps.md`](tracked-gaps.md).
