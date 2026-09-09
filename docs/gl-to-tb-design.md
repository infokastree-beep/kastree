# Phase 3 — General Ledger → Trial Balance (design)

Status: **BUILT** (2026-09-09) — free in-flow Upload path.  
Demand: **confirmed** (client, own words) — GL dump (PDF or Excel) → Excel + trial balance, quickly.

> “sometimes all I have is a general ledger dump of transactions in either PDF
> or Excel, I want to be able to convert this into Excel and also into trial
> balance so I can do it quickly and immediately.”

## Scope confirmation (locked)

| # | Capability | In scope |
|---|------------|----------|
| 1 | PDF **or** Excel/CSV GL upload | Yes |
| 2 | Period-end prompt (and period-start — see below) | Yes |
| 3 | Actual GL→TB conversion (bucket by GL code; period cutoff; opening-balance semantics) | Yes |
| 4 | Mandatory debit = credit validation; clear error on failure; **block** pipeline | Yes |
| 5 | Mandatory review step before resulting TB enters existing Upload → map → statements pipeline | Yes |

**Product shape:** FREE, included in Kastree subscription — same integrated approach as
Phase 1 PDF-TB (`Upload` selector → extract/convert → review → existing pipeline).

**Explicitly out of this build:**

- Standalone Kastree Convert (`/solutions/convert`) does **not** gain GL→TB.
  Convert remains TB-only for non-subscribers.
- No LLM math. Python `Decimal` only for all amounts.
- No silent “best guess” on opening balances or cutoffs.

## Placement

Extend signed-in **Upload** (same pattern as PDF-TB):

```
What are you uploading?
  ○ Trial balance (Excel / CSV)
  ○ Trial balance (PDF)          ← Phase 1, shipped
  ○ General ledger (Excel / CSV) ← Phase 3
  ○ General ledger (PDF)         ← Phase 3
```

Not a second paid product. Not a marketing-Solutions entry.

## End-to-end flow

```
[Upload: GL Excel/PDF]
        │
        ▼
[Period & opening-balance questionnaire — required, no skip]
  • period_start  (date)
  • period_end    (date)     ← becomes trial_balances.period_end
  • opening_balance_mode     ← A / C recommended; B restricted
        │
        ▼
[Parse / extract ledger lines]
  Excel/CSV → column map (date, code, name, debit, credit)
  PDF → pdfplumber / OCR → same line schema (reuse Phase 1 extract patterns;
        new target shape = transactions, not TB rows)
        │
        ▼
[Deterministic GL→TB engine — Python Decimal]
  1. Classify / filter lines by mode + dates (see § Opening balances & cutoffs)
  2. Bucket by GL code (+ name)
  3. Produce candidate TB rows
  4. Validate Σ debit == Σ credit within €0.01
        │
        ├── FAIL → hard stop. Show imbalance, excluded-line counts, top accounts.
        │          User may fix source / dates / mode and re-run. No TB created.
        │
        ▼ PASS
[Review UI — mandatory]
  • Editable TB rows (code, name, debit, credit)
  • Read-only provenance strip: mode, period_start/end, included/excluded counts
  • Optional: download structured GL Excel (client ask: “into Excel and also TB”)
        │
        ▼ Confirm
[Existing pipeline unchanged]
  Confirmed TB as CSV/xlsx → same /upload path as today → mapping → statements
```

Extract/convert creates **no** `trial_balances` row until after review confirm
(same safety contract as Phase 1).

---

## Correctness-critical: period cutoffs & opening balances

Bucket-by-code is the easy part. **Wrong opening-balance assumption → wrong
closing TB every time.** The product must **never** infer this silently.

### Required inputs (always)

| Field | Rule |
|-------|------|
| `period_end` | Required. Stored as `trial_balances.period_end`. |
| `period_start` | Required for GL path. Inclusive start of the reporting window. |
| `opening_balance_mode` | Required enum — user must choose. No implicit default that invents openings. |

Date filter (all modes), for **movement** lines:

```
include movement ⇔  period_start  ≤  txn_date  ≤  period_end
```

- Dates **after** `period_end` → **excluded** (never silently included). Count shown.
- Dates **before** `period_start` → handled per mode (never silently treated as
  in-period movements).
- Missing / unparseable dates → **fail closed** into a “needs attention” bucket;
  cannot confirm review until resolved or explicitly discarded by the user.

Tolerance for TB balance check: `TOLERANCE = Decimal("0.01")` (existing product rule).

### Opening-balance modes

#### Mode C — **Year-to-date / full ledger through period end** (recommended default UX)

**When to use:** Export covers activity from the start of the financial window
through `period_end` (typical “YTD GL dump” or “ledger for the year”).

**Assumption (stated in UI, user must confirm):** At `period_start`, accounts
are zero **or** any opening journals are **inside** the file as dated lines on
or after `period_start`.

**Math per account:**

```
included = lines where period_start ≤ date ≤ period_end
TB_net   = Σ debit − Σ credit   (Decimal)
```

Present as one-sided TB row (debit XOR credit), same as Phase 1 review rows.

**Why this matches the client ask:** One GL dump → closing TB for `period_end`
without a separate opening file, when the dump is genuinely YTD/FY-to-date.

#### Mode A — **File includes opening / brought-forward rows**

**When to use:** Export has explicit opening lines (labels such as Opening,
Brought forward, B/fwd, Balance b/d, Opening balance, OB) **plus** period
movements.

**Classification:**

1. Tag **opening rows** by label heuristics (conservative; ambiguous → review).
2. Opening rows are **not** date-filtered the same way; they seed the account.
3. Movement lines: `period_start ≤ date ≤ period_end` only.

**Math per account:**

```
OB_net       = Σ debit − Σ credit   on opening-tagged rows for that account
movement_net = Σ debit − Σ credit   on included movement lines
TB_net       = OB_net + movement_net
```

If an account has movements but no opening row → OB = 0 for that account
(explicit in provenance). If opening rows exist with dates after `period_end` →
error (nonsensical).

#### Mode B — **Period movements only (no openings)** — restricted

**When to use:** File truly has only this period’s postings, no openings, not YTD.

**Math:** Same date filter as Mode C, **but** the result is a **period movement
schedule**, not a full closing TB for balance-sheet accounts.

**Product rules for Mode B:**

1. Strong warning in UI: BS closing positions will be wrong unless openings are
   zero or supplied another way.
2. **Cannot** proceed to pipeline confirm unless the user either:
   - switches to Mode A or C, **or**
   - supplies a **prior closing TB** for the same company with
     `prior.period_end == day before period_start` (or equal to last closed
     period we can match), which we apply as openings:

```
TB_net = prior_TB_net + period_movement_net   (per account; accounts only in
         movements inherit 0 prior; accounts only in prior with no movements
         carry prior forward)
```

3. Without prior TB, Mode B may still allow **download of structured GL Excel +
   movement schedule** for inspection, but **blocks** “Confirm into statements.”

This prevents the classic failure mode: month-only GL → “TB” → SOFP nonsense.

### Period-end edge cases (explicit)

| Case | Behaviour |
|------|-----------|
| `period_start > period_end` | Reject before parse. |
| Duplicate TB for same `client`/`company` + `period_end` | Existing **409** UNIQUE rule — unchanged. |
| Lines on `period_end` date | **Included** (inclusive end). |
| Lines on `period_start` date | **Included** as movements (Mode A openings still separate). |
| Timezones | Dates only (no timestamps) for MVP; parse as calendar dates. |
| Credit/debit swapped columns | Detect via header synonyms; if ambiguous, stop for column mapping UI. |
| Signed single “amount” column | Supported: positive → debit, negative → credit (or configurable); Documented in parser. |

### Debit = credit gate

After bucketing:

```
Σ TB debits − Σ TB credits  ≤  €0.01 in absolute value
```

On failure:

- HTTP/UI: clear error, imbalance amount, top N accounts by absolute net.
- Show included vs excluded line counts and mode/dates used.
- **No** review-confirm CTA that enters `/upload`.
- User must change inputs or fix source data and re-run.

On pass: proceed to mandatory review (user may still edit rows; **re-validate**
debit=credit on confirm — edits that unbalance block confirm again).

### Review → pipeline

Same contract as Phase 1:

- Review table editable.
- Confirm builds TB file (CSV/xlsx) and posts through existing Upload path.
- Mapping / statements / variance / commentary unchanged.
- Provenance metadata retained on the job (mode, period_start/end, source
  filename, included/excluded counts) for audit.

### Dual delivery (client wording)

From one successful convert:

1. **Structured GL Excel** — cleaned transaction lines (optional download on
   review screen).
2. **Trial balance** — after confirm, into the Product 1 pipeline (and
   downloadable from review).

---

## Engine sketch (deterministic)

```text
parse_gl(file) → list[GlLine{date, code, name, debit, credit, raw_flags}]
classify(lines, mode) → openings[], movements[], rejected[]
filter_movements(movements, period_start, period_end) → included[], excluded[]
aggregate(openings, included) → list[TbRow]
assert_balanced(tb_rows) → ok | ImbalanceError
```

No floats. No LLM for amounts. PDF path: extract to `GlLine` first, then same
engine as Excel (one conversion core).

## Tests required before ship (non-negotiable)

1. Mode C: balanced YTD fixture → balanced TB; line after `period_end` excluded.
2. Mode A: OB + movements → TB equals OB+movements per account.
3. Mode B without prior TB → cannot confirm into pipeline.
4. Mode B with prior TB → carry-forward + movements = expected closing.
5. Imbalanced GL → validation error, no TB row created.
6. Review edit that breaks balance → confirm blocked.
7. PDF GL and Excel GL hit the **same** aggregate/validate functions.
8. Subscriber Upload path only; Convert routes unchanged (no GL→TB).

## Status vs roadmap

Prior note: Phase 3 unscheduled pending **separate** GL demand.  
**This document records that demand as confirmed** and freezes the correctness
model above. Implementation starts only after design approval (especially Mode
A/B/C and Mode B’s prior-TB rule).
