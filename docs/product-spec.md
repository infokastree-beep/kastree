# FinDraft

**Product Specification v3.2**

Financial Intelligence Layer for Accounting Practices

**Date:** 29 August 2026 | **Status:** DRAFT FOR REVIEW

**Version:** 3.2 | **Supersedes v3.1

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 28 Aug 2026 | Baseline locked spec |
| 3.0 | 29 Aug 2026 | Extended timeline (8→12 weeks), added GDPR compliance, complete API spec, feature tier matrix, audit_logs / processing_jobs / subscription_events tables, realistic success metrics, deployment strategy, data retention policies |
| 3.1 | 29 Aug 2026 | Independent verification of v3.0's fixes found 6 partially-closed gaps and 1 new inconsistency. This version closes them: (1) Appendix B's tier-differentiated materiality default removed — schema only supports one default; (2) RLS section now shows the join-based policy pattern needed for every table that isn't org_id-direct (all of them except clients, audit_logs, notifications); (3) export file retention separated from statement data retention (6yr data, 30-day file, regenerate on demand — the unqualified reading would have reintroduced the S3 cost problem this section was written to prevent); (4) currency detection priority order specified; (5) updated_at added to risk_flags, commentary_feedback, notifications; (6) UNIQUE(client_id, period_end) constraint added to trial_balances; (7) /notifications routes added to the UI route map; (8) Cursor AI Rules §7.1/§7.3 model-selection disagreement on risk-explanation routing resolved. |
| 3.2 | 29 Aug 2026 | Merged in the legitimate parts of a separately-drafted Irish compliance addendum (which had been built on unfixed v3.0, not v3.1 — all of v3.1's six fixes above are retained here). Added: an archived_records table for immutable 7-year WORM-style archival (Section 9.1); a corrected version of the TB-balance database trigger from that addendum, whose original JSONB path didn't match this document's own validation_results shape and would have silently never fired (Section 9.1); a Data Processing Agreement / sub-processor register section listing SCC and Transfer Impact Assessment requirements for OpenAI, Stripe, Clerk, and Resend (Section 12.3); a PSD2/Open Banking section confirming it's out of MVP scope (Section 12.4); retention policy reframed as 7 years = the 6-year statutory minimum (Companies Act 2014 §285 / Taxes Consolidation Act 1997 §886) plus a 1-year engineering buffer, stated honestly as a safety margin rather than the addendum's incorrect claim that 7 years is itself the legal minimum. Removed from the addendum: a fabricated 'DPC registration' requirement (with an invented €40 fee) that appeared in three places in the source document, including — most importantly — the pricing/feature-tier matrix, where it would have shown paying customers a false regulatory compliance claim. DPC registration was abolished under GDPR in May 2018 and does not exist as a requirement to reintroduce. |

---

## 1. Executive Summary

FinDraft is a web-based financial intelligence platform for UK and Ireland accounting practices and fractional CFOs. Users upload a client's trial balance (Excel/CSV) and receive auto-generated Statement of Profit or Loss (SOPL), Statement of Financial Position (SOFP), Statement of Changes in Equity (SOCIE), period-on-period variance analysis with AI-drafted commentary, and automated risk flags — all reviewable and editable in an interactive dashboard before export to Excel, CSV, or PDF.

**Golden Rule: Python does the math. LLM does the narrative. Never the reverse. All financial calculations are deterministic, auditable, and accurate to the penny.**

**MVP Timeline:** 12 weeks (solo founder). See Section 14 for phased milestones.

**Target Market:** UK and Ireland (Phase 1). Expansion to US, Australia, Canada in Phase 2 (Month 6+).

---

## 2. Target User & Persona

### Primary User

Partner, Manager, or Outsourced CFO at a small-to-mid accounting practice (5–50 staff) or fractional CFO firm (1–5 people serving 10–30 clients).

### Demographics

- Age: 30–55
- Location: UK and Ireland (Phase 1)
- Tech Comfort: High — lives in Excel daily. Expects formulas, formatting, and control.
- Regulatory Context: ICAEW / ACCA / CIMA member. Requires audit trails and data protection compliance.

### Pain Points

1. Spends 2–4 hours per client per month building management accounts from scratch in Excel.
2. Writes variance commentary manually — repetitive and time-consuming.
3. Misses anomalies because of time pressure and lack of automated checks.
4. Receives trial balances in inconsistent formats from clients — no standardisation.
5. Needs board-ready packs quickly for client meetings.

### Jobs-to-be-Done

- "I want to upload a messy Excel TB and get clean financial statements in under 2 minutes."
- "I want AI-drafted commentary that I can edit, not write from scratch."
- "I want to catch errors and anomalies before my client sees them."
- "I want my team to collaborate on the same client files without version chaos."

---

## 3. Core Problem Statement

Accounting practices receive client trial balances in inconsistent Excel formats every month. Building SOPL/SOFP/SOCIE, checking reconciliation, writing variance commentary, and flagging risks is manual, repetitive, and error-prone. There is no software that accepts any Excel trial balance without API integration and produces a clean, auditable analysis pack in under 60 seconds.

FinDraft solves this by:

1. Parsing any Excel/CSV TB format automatically.
2. Mapping accounts to canonical categories using a hybrid AI + heuristic approach.
3. Generating deterministic financial statements with full evidence provenance.
4. Drafting variance commentary via LLM (with human review mandatory before export).
5. Flagging risks automatically using deterministic rules.

---

## 4. MVP Scope — IN

### 4.1 Input Layer

| Feature | Description | Tier |
|---------|-------------|------|
| TB Upload | Single Excel (.xlsx) or CSV file upload. Supports: standard 4-column (Account Code, Name, Debit, Credit), single Balance column (+/-), multi-tab workbooks (first tab default, tab selector if >1 tab). | All |
| Prior Period Upload | Optional separate upload of prior period TB. Same format support. Auto-detected by most recent period_end < current TB. Manual override available. | All |
| Multi-Currency | Functional currency per client (GBP, EUR, USD). Currency symbol auto-detected (£, €, $, or text "GBP"/"EUR"/"USD"). All calculations in Decimal. Manual override in upload UI. | All |
| Auto Column Detection | Parser detects Account Code, Account Name, Debit, Credit columns. Confidence score 0.0–1.0. Falls back to manual column mapping UI if confidence < 0.80. | All |
| File Validation | Type check (.xlsx, .csv only), size check (max 50MB), virus scan (ClamAV via python-clamd), structure check (min 3 data rows). | All |

#### Currency Detection Priority (v3.1 — closes a gap left open in v3.0)

"Auto-detected" on its own doesn't say what happens when detection is ambiguous. Detection runs in this priority order and stops at the first match:

1. Explicit column header (e.g. a "Currency" column, or a header cell containing "GBP"/"EUR"/"USD").
2. A currency symbol (£, €, $) found in the first 100 scanned cells.
3. Fall back to the client's stored functional currency default.

If step 2 finds more than one distinct symbol across the scanned cells, log the ambiguity (do not silently pick one) and require the user to confirm currency in the upload UI before parsing proceeds. The manual override in the upload UI is always available regardless of which detection path fired.

#### Parser Behaviour

- Merged cells: auto-unmerge and forward-fill. Log warning.
- Header rows: skip rows where first cell contains "Account", "Code", "Description", etc.
- Totals rows: skip rows where account name contains "Total", "Balance", "Sum" (case-insensitive).
- Blank rows: skip entirely blank rows.
- Currency symbols: strip £€$ during parsing. Store detected currency per account.
- Negative balances: preserve sign. Flag anomalies (e.g., revenue account with debit balance) in risk report.

### 4.2 Engine Layer

| Feature | Description |
|---------|-------------|
| TB Parser | pandas-based with Decimal arithmetic. Chunked reading for files >5MB. Returns List[TBRow] with account_code, account_name, debit, credit, net_balance, currency, row_index. |
| Hybrid Account Mapper | 4-tier mapping: (1) Exact match to client's prior confirmed mappings, (2) Fuzzy string match (Levenshtein ratio ≥0.85), (3) Code range heuristics (1000-1999=assets, 4000-4999=revenue, etc.), (4) LLM tie-breaker (GPT-4o-mini) for unmapped accounts only. LLM receives account names and codes only — NO monetary values. |
| Mapping Review UI | Interactive table: source code, source name, suggested canonical line, confidence badge (green ≥0.85, amber 0.60–0.84, red <0.60), method tag, inline edit dropdown. Unmapped accounts pinned to top. "Apply to All Similar" token-based bulk action. "Remember for [Client]" toggle saves confirmed mapping. |
| 5 Validation Checks + 1 Status Flag | See Section 4.2.1 below. |
| Statement Builder | Deterministic SOPL, SOFP, SOCIE generation from mapped accounts. Standard UK layout. Subtotals in Python only. Evidence graph links every line item to source TB rows. |

#### 4.2.1 Validation Checks (Deterministic, Decimal Only)

| # | Check Name | Rule | Severity | Blocks Export? |
|---|------------|------|----------|----------------|
| 1 | TB Integrity | Total debits = total credits within €0.01 (or functional currency equivalent) | Error | Yes |
| 2 | Balance Sheet Balance | Total assets = total liabilities + total equity within €0.01 | Error | Yes |
| 3 | Retained Earnings Roll-forward | If prior period provided: closing RE prior + current period profit = closing RE current within €0.01 | Warning | No |
| 4 | Net Assets Check | Net assets (assets − liabilities) = share capital + opening retained earnings + current-period profit within €0.01. Opening RE is the TB retained_earnings balance; period profit is the same SOPL net_profit figure (see statements.compute_net_profit). Un-closed Dividends are deliberately excluded from this equity total so the check stays independent of Balance Sheet Balance — open Dividends fail net_assets by exactly the dividend amount. | Error | Yes |
| 5 | Negative Cash/Bank | Any cash/bank account with net_balance < 0 | Warning | No |
| 6 | Comparatives Available (Status Flag, not validation) | Prior period TB exists for this client | Info | No |

**Validation Flow:**

1. Run checks 1, 2, 4 first (structural integrity). If any fail, block statement generation. Show error with difference amount.
2. Run checks 3, 5 (analytical). Generate warnings. Do not block.
3. Set flag 6. Enable/disable variance analysis tab accordingly.

### 4.3 Intelligence Layer

| Feature | Description | Tier |
|---------|-------------|------|
| Variance Analysis | Period-on-period comparison (current vs prior TB). Materiality: >10% OR >1,000 functional currency units. Flags: increase, decrease, new, removed. | All |
| AI Commentary — Material Variances | GPT-4o drafts 1–2 sentence explanations per material variance. Structured JSON output. Temperature 0.2. No monetary amounts in prompt — only account names, directions, and percentages. User must review before export. | Pro+ |
| AI Commentary — Business Health | GPT-4o drafts 3-bullet executive summary: gross margin trend, operating leverage, cash position, 2–3 key takeaways. Based on statement-level trends only. No raw numbers in prompt. | Pro+ |
| Evidence Graph | Every statement line item links to source TB rows. Click "View Source" to see contributing accounts. MVP: TB row-level. Stored as source_account_ids array in statement_line_items. | All |
| AI Reasoning Display | Each AI commentary shows "Why this was drafted" tooltip with LLM reasoning. Thumbs up/down. Downvotes logged to commentary_feedback. | Pro+ |
| Risk Heatmap | 2 rules: (1) Negative Cash/Bank (any cash account with net < 0), (2) Unusual Variance (>3 standard deviations from 12-month average if available; fallback to >50% if 3–11 months; skip if <3 months). Severity: warning. | Starter+ |

*Note on AI Commentary Tiers: Starter and Free tiers receive variance analysis (calculated numbers + direction flags) but NO AI-drafted text. The UI shows "Upgrade to Pro for AI commentary" placeholder. This is a deliberate product decision to drive upgrade conversion.*

### 4.4 Output Layer

| Feature | Description | Tier |
|---------|-------------|------|
| Excel Export | Formatted workbook: SOPL, SOFP, SOCIE, Variance, Risk, Mapping Summary sheets. Professional styling. Company branding area (client name, period end, generated date). No formulas in MVP. | Starter+ (Free: watermarked) |
| CSV Export | Flat CSV of all statement line items with metadata. | All |
| PDF Export | Board-ready pack: cover page, TOC, all sections. Watermarked on Free tier. | Starter+ (Free: watermarked) |
| Interactive Dashboard | Web-based review: SOPL/SOFP/SOCIE tabs, variance table, risk heatmap. Inline editing of commentary and manual statement overrides. Export trigger. | All |

### 4.5 Platform, Auth & Compliance

| Feature | Description |
|---------|-------------|
| Organisation Model | Multi-user orgs. Roles: Owner (full control), Admin (manage users/clients), Member (upload/review/export), Viewer (view only). |
| Client Workspaces | Each client is a separate workspace. Mappings remembered per client. Historical TBs stored per client. Soft delete supported. |
| Async Processing | All heavy operations run async. State machine: pending → parsing → mapping → validating → generating → analysing → complete/failed. Progress via SSE (fallback to polling). Max 3 concurrent jobs per org. Queue position shown if limit reached. |
| Stripe Billing | Self-serve subscription management. Free / £49 Starter / £149 Pro / £349 Scale. Webhook handling for payment events. Feature gating by real-time subscription status. |
| GDPR Compliance | UK & Irish GDPR compliance built-in, including Companies Act 2014 / Revenue retention. See Section 12. |
| Audit Logging | All mutations to mappings, statements, commentary, and exports logged with user ID, timestamp, IP, old/new values. See audit_logs table. |
| Notifications | Email notifications: processing complete, export ready, validation failure, LLM unavailable. Via Resend. |

---

## 5. MVP Scope — EXPLICITLY OUT

The following are NOT in MVP scope. Do not build. Do not design data models for these until scheduled.

- General ledger transaction-level analysis (line-item transactions, not TB summary)
- Cash flow forecasting
- Scenario modelling / 'what-if' sliders
- Budget upload and budget-vs-actual variance (framework in place, UI deferred to Month 4)
- Direct API integrations (Xero, QuickBooks, Sage)
- Aged debtor / creditor reports (TB doesn't contain this data)
- Related-party transaction detection
- Going concern assessment
- Industry benchmarking / external data
- Predictive analytics / macroeconomic modelling
- White-label PDF branding (deferred to Scale tier, Month 6+)
- API access for external integrations
- Native mobile app (responsive web only)
- Multi-entity consolidation
- FX revaluation automation
- Custom chart of accounts (uses canonical mapping only)

---

## 6. Key User Workflows

### 6.1 First-Time User Flow

1. Sign up via Clerk auth (email, Google, Microsoft).
2. Create organisation — name, functional currency default.
3. Invite team (optional) — send email invites. Roles assigned.
4. Add first client — name, company number, industry, functional currency.
5. Upload current period TB — drag-drop or file picker. System parses, auto-detects columns.
6. Column mapping fallback (if confidence < 0.80) — user maps columns manually.
7. Mapping review — review suggested account mappings. Edit, bulk-apply, confirm.
8. Generate statements — async processing begins. Progress bar: Parsing → Mapping → Validating → Generating → Analysing → Complete.
9. Dashboard review — SOPL, SOFP, SOCIE tabs. Variance tab (if prior period uploaded). Risk tab. Edit commentary inline.
10. Export — select format, trigger background generation, receive email + download link.

*Time target: First statement pack within 5 minutes of upload for a standard TB.*

### 6.2 Monthly Recurring Flow (Power User)

1. Navigate to existing client → click "Upload New Period".
2. Upload new TB → prior mappings auto-applied → only new/changed accounts need review.
3. System auto-detects prior period TB (most recent by period_end).
4. Dashboard loads with variance commentary pre-drafted (Pro tier).
5. Review, edit commentary, check risk flags.
6. Export → send to client.

*Time target: Under 3 minutes for recurring client with no new accounts.*

### 6.3 Mapping Review & Edit Flow

1. Mapping table shows all accounts from uploaded TB (paginated, 50 rows default).
2. Unmapped accounts pinned to top with red "Unmapped" badge.
3. Each row: Source Code | Source Name | Suggested Canonical Line | Confidence % | Method | Action
4. Action dropdown: Accept | Edit (dropdown of all canonical lines) | Ignore (moves to suspense/unmapped)
5. "Apply to All Similar" — token-based match (split name on non-alphanumeric, match any token). Shows preview of affected accounts. Undo available.
6. "Remember for [Client Name]" toggle — saves confirmed mapping to account_mappings with is_confirmed = TRUE.
7. LLM reasoning shown in tooltip for any LLM-suggested mapping.
8. Search/filter bar: filter by source code, source name, canonical line, or confidence range.

### 6.4 Validation Failure Flow

1. User clicks "Generate Statements".
2. Validation runs. If Check 1, 2, or 4 fails: show error banner with specific check name and difference amount; block statement generation; provide "Download Error Report" (CSV of failing checks); suggest fix source file and re-upload, or add suspense account.
3. If Check 3 or 5 fails: show warning banner; allow statement generation with warning acknowledged; include warning in risk report.

### 6.5 Export Flow

1. User clicks "Export" on dashboard.
2. Select format: Excel (sheets listed), PDF, CSV.
3. Select options: include mapping summary (yes/no), include risk report (yes/no).
4. Trigger background export job. Show "Processing" state.
5. System generates file → uploads to S3/R2 → updates exports table.
6. Email sent: "Your export is ready." + in-app notification.
7. User clicks download link (signed URL, 1-hour expiry).
8. Free tier: PDF includes "Generated by FinDraft" watermark.

---

## 7. Edge Cases & Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Unbalanced TB | Block statement generation. Show error with difference amount. User must fix source file or add suspense account. |
| <50% accounts mapped | Pause and show mapping review. Do not generate statements. Show: "X of Y accounts unmapped. Please review mappings." |
| Missing prior period | Disable variance analysis. Show info banner: "Upload prior period TB to enable variance analysis." SOPL/SOFP/SOCIE still generated. |
| Multi-tab Excel | Parse first tab by default. If <3 data rows, attempt second tab. Show tab selector if multiple tabs detected. |
| Merged cells | Auto-unmerge and forward-fill. Log warning: "Merged cells detected in rows X–Y. Values inferred." |
| Foreign currency symbols | Detected per the priority order in Section 4.1. All calculations in Decimal with 2 decimal places. |
| Negative balances in revenue/costs | Flag as anomaly in risk report. Do NOT block. Include in "Negative Cash/Bank" or "Anomalous Balance Direction" risk. |
| Duplicate account names | Treat as separate if codes differ. Show both in mapping table with codes visible. |
| Large files (>10MB) | Accept up to 50MB. Warning: "Large file detected. Processing may take longer." Chunked parsing. |
| LLM timeout/failure | After 4 total call attempts (1 initial + 3 retries, exponential backoff 1s/2s/4s), generate statements without AI commentary. Banner: "AI commentary temporarily unavailable. Statements are complete." Log error. |
| Concurrent uploads | Queue per org. Max 3 concurrent processing jobs. Show queue position if limit reached. |
| Duplicate upload (same period) | trial_balances has a UNIQUE(client_id, period_end) constraint (Section 9.1, added in v3.1) — a second upload for a period that already exists is rejected at the API layer with: "A trial balance for this period already exists for this client. Delete the existing one first, or choose a different period end date." This replaces the v3.0 file-hash duplicate check, which only caught identical files, not a genuinely different file uploaded for a period that's already been processed. |
| User edits statement line item | Store override in statement_line_items with is_manual_override = TRUE, overridden_by_user_id, original_value. Include in audit log. |
| User edits commentary | Store corrected text in variance_analyses.commentary with is_edited = TRUE, edited_by_user_id. Original AI text preserved. |
| Export generation fails | Status = failed. Show retry button. Log error. Notify user via email. |
| Session expiry during upload | Save upload progress to processing_jobs. On re-login, resume from current step. |
| Org member removed mid-session | Immediate revocation on next API call (JWT expiry 15 min). No long-lived sessions. |

*Note (v3.1): the "Duplicate upload" row above replaces v3.0's file-hash-only check. file_hash is still stored and still used to detect a byte-identical re-upload (fast path, no DB constraint violation needed), but the period-level UNIQUE constraint is the actual guarantee — it catches a different file for an already-used period, which the hash check alone would have missed.*

---

## 8. Tech Stack (Locked)

| Layer | Technology | Version | Rationale |
|-------|------------|---------|-----------|
| Frontend | Next.js | 14 (App Router) | Server Components by default, SEO, performance |
| | TypeScript | 5.3+ | Type safety |
| | Tailwind CSS | 3.4 | Rapid styling |
| | shadcn/ui | latest | Accessible, composable components |
| | TanStack Query | v5 | Server state management |
| | Zustand | latest | Client UI state |
| Backend | FastAPI | 0.110+ | Async Python, auto OpenAPI docs |
| | Python | 3.11+ | Performance, type hints |
| | Pydantic | v2 | Validation, settings management |
| | SQLAlchemy | 2.0 | Async ORM |
| | Alembic | latest | DB migrations |
| Database | PostgreSQL | 15 | JSONB, RLS, reliability |
| | psycopg2-binary | latest | Sync fallback |
| | asyncpg | latest | Async driver |
| AI/LLM | OpenAI SDK | 1.0+ | Structured output, function calling |
| | GPT-4o | latest | Primary model for commentary |
| | GPT-4o-mini | latest | Fallback for mapping tie-breaker and risk explanations (v3.1: scope aligned with Cursor AI Rules §7.1/§7.3) |
| Excel | OpenPyXL | 3.1+ | Formatting, styling, multi-sheet |
| PDF | WeasyPrint | 60+ | HTML+CSS→PDF |
| Auth | Clerk | @clerk/nextjs | Orgs, roles, MFA, webhooks |
| File Storage | AWS S3 or Cloudflare R2 | latest | Signed URLs, lifecycle policies |
| Queue/Async | FastAPI BackgroundTasks | MVP | Simple, no infra overhead |
| | Celery + Redis | Month 3+ | If volume exceeds BackgroundTasks |
| Email | Resend | latest | Developer-friendly, good deliverability |
| Monitoring | Sentry | latest | Error tracking |
| | Logtail | latest | Log aggregation |
| Testing | pytest | 8+ | Unit + integration |
| | pytest-asyncio | latest | Async test support |
| | Factory Boy | latest | Test data |
| | pytest-cov | latest | Coverage |
| | Playwright | latest | E2E testing (Month 2+) |

**Hosting:**

- Frontend: Vercel (production + preview deployments)
- Backend: Railway or Render (production + staging)
- Database: Railway PostgreSQL or Render PostgreSQL
- Staging environment required before production deploys.

---

## 9. Database Schema (Full DDL)

*v3.1 changes in this section: updated_at added to risk_flags, commentary_feedback, and notifications (all three have mutable fields and were missing it in v3.0); UNIQUE(client_id, period_end) added to trial_balances; Section 9.2 (RLS) rewritten to show the join-based policy pattern actually needed by every table below except clients, audit_logs, and notifications. v3.2 additions: archived_records table for immutable 7-year archival (WORM pattern, append-only like audit_logs); a corrected TB-balance database trigger, since a version proposed elsewhere checked a JSONB key that does not match this document's own validation_results shape and would have silently never fired; archived_records added to the direct-org_id RLS group in Section 9.2.*

### 9.1 Core Entities

```sql
-- Organisations
CREATE TABLE organisations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clerk_org_id VARCHAR UNIQUE NOT NULL,
  name VARCHAR NOT NULL,
  subscription_tier VARCHAR NOT NULL DEFAULT 'free' CHECK (subscription_tier IN ('free','starter','pro','scale')),
  subscription_status VARCHAR NOT NULL DEFAULT 'active' CHECK (subscription_status IN ('active','past_due','cancelled','trialing')),
  stripe_customer_id VARCHAR,
  stripe_subscription_id VARCHAR,
  functional_currency VARCHAR(3) NOT NULL DEFAULT 'GBP',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_organisations_clerk_org_id ON organisations(clerk_org_id);
CREATE INDEX idx_organisations_stripe_customer ON organisations(stripe_customer_id);

-- Users
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clerk_user_id VARCHAR UNIQUE NOT NULL,
  org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
  email VARCHAR NOT NULL,
  role VARCHAR NOT NULL CHECK (role IN ('owner','admin','member','viewer')),
  last_login_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_users_clerk_user_id ON users(clerk_user_id);
CREATE INDEX idx_users_org_id ON users(org_id);

-- Clients
CREATE TABLE clients (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
  name VARCHAR NOT NULL,
  company_number VARCHAR,
  industry VARCHAR,
  functional_currency VARCHAR(3) NOT NULL DEFAULT 'GBP',
  materiality_threshold_pct NUMERIC(5,2) NOT NULL DEFAULT 10.00,
  materiality_threshold_abs NUMERIC(19,2) NOT NULL DEFAULT 1000.00,
  is_deleted BOOLEAN DEFAULT FALSE,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_clients_org_id ON clients(org_id);
CREATE INDEX idx_clients_org_deleted ON clients(org_id, is_deleted);
```

*Note (v3.1): materiality_threshold_pct/abs default to the same values (10.00 / 1000.00) regardless of subscription tier. Appendix B previously implied Pro/Scale customers get a different default (5% / 500) — that tier-conditional default doesn't exist in this schema or anywhere in the onboarding flow, so Appendix B has been corrected to match what's actually built: one default, editable per client on any tier.*

```sql
-- Trial Balances
CREATE TABLE trial_balances (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  period_end DATE NOT NULL,
  period_start DATE,
  file_url VARCHAR NOT NULL,
  file_type VARCHAR NOT NULL CHECK (file_type IN ('xlsx','csv')),
  file_size_bytes INTEGER,
  file_hash VARCHAR(64),
  raw_data JSONB,
  parsed_data JSONB,
  status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','parsing','mapping','validating','generating','analysing','complete','failed')),
  currency VARCHAR(3),
  validation_results JSONB,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(client_id, period_end) -- NEW in v3.1: closes M8, prevents two TBs for the same period
);
CREATE INDEX idx_trial_balances_client_id ON trial_balances(client_id);
CREATE INDEX idx_trial_balances_client_period ON trial_balances(client_id, period_end);
CREATE INDEX idx_trial_balances_status ON trial_balances(status);

-- Account Mappings
CREATE TABLE account_mappings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  source_code VARCHAR,
  source_name VARCHAR NOT NULL,
  canonical_line VARCHAR NOT NULL,
  confidence NUMERIC(3,2),
  method VARCHAR NOT NULL CHECK (method IN ('exact','fuzzy','code_range','llm','manual')),
  is_confirmed BOOLEAN DEFAULT FALSE,
  is_ignored BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(client_id, source_code, source_name)
);
CREATE INDEX idx_account_mappings_client_id ON account_mappings(client_id);
CREATE INDEX idx_account_mappings_client_confirmed ON account_mappings(client_id, is_confirmed);

-- Financial Statements
CREATE TABLE financial_statements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tb_id UUID NOT NULL REFERENCES trial_balances(id) ON DELETE CASCADE,
  statement_type VARCHAR NOT NULL CHECK (statement_type IN ('SOPL','SOFP','SOCIE')),
  data JSONB NOT NULL,
  generated_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_financial_statements_tb_id ON financial_statements(tb_id);
CREATE INDEX idx_financial_statements_tb_type ON financial_statements(tb_id, statement_type);

-- Statement Line Items (normalized for evidence graph)
CREATE TABLE statement_line_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  statement_id UUID NOT NULL REFERENCES financial_statements(id) ON DELETE CASCADE,
  line_item_code VARCHAR NOT NULL,
  line_item_name VARCHAR NOT NULL,
  amount NUMERIC(19,2) NOT NULL,
  is_subtotal BOOLEAN DEFAULT FALSE,
  is_manual_override BOOLEAN DEFAULT FALSE,
  overridden_by_user_id UUID REFERENCES users(id),
  original_amount NUMERIC(19,2),
  source_account_ids UUID[],
  display_order INTEGER NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_statement_line_items_statement_id ON statement_line_items(statement_id);
CREATE INDEX idx_statement_line_items_source_accounts ON statement_line_items USING GIN(source_account_ids);

-- Variance Analyses
CREATE TABLE variance_analyses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tb_id UUID NOT NULL REFERENCES trial_balances(id) ON DELETE CASCADE,
  prior_tb_id UUID REFERENCES trial_balances(id) ON DELETE SET NULL,
  items JSONB NOT NULL,
  commentary JSONB,
  status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','generating','complete','failed')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_variance_analyses_tb_id ON variance_analyses(tb_id);
CREATE INDEX idx_variance_analyses_prior_tb ON variance_analyses(prior_tb_id);

-- Risk Flags
CREATE TABLE risk_flags (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tb_id UUID NOT NULL REFERENCES trial_balances(id) ON DELETE CASCADE,
  rule_name VARCHAR NOT NULL,
  severity VARCHAR NOT NULL CHECK (severity IN ('warning','critical')),
  description VARCHAR NOT NULL,
  affected_accounts JSONB,
  recommended_action TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW() -- NEW in v3.1: severity/description are editable by a reviewer
);
CREATE INDEX idx_risk_flags_tb_id ON risk_flags(tb_id);
CREATE INDEX idx_risk_flags_tb_severity ON risk_flags(tb_id, severity);

-- Exports
CREATE TABLE exports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tb_id UUID NOT NULL REFERENCES trial_balances(id) ON DELETE CASCADE,
  format VARCHAR NOT NULL CHECK (format IN ('xlsx','csv','pdf')),
  file_url VARCHAR,
  status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','complete','failed')),
  options JSONB,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_exports_tb_id ON exports(tb_id);
CREATE INDEX idx_exports_status ON exports(status);

-- Commentary Feedback
CREATE TABLE commentary_feedback (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  variance_id UUID NOT NULL REFERENCES variance_analyses(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  line_item_code VARCHAR NOT NULL,
  thumbs_up BOOLEAN,
  corrected_text TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW() -- NEW in v3.1: corrected_text is editable after initial submission
);
CREATE INDEX idx_commentary_feedback_variance ON commentary_feedback(variance_id);
CREATE INDEX idx_commentary_feedback_user ON commentary_feedback(user_id);

-- Audit Logs
CREATE TABLE audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
  action VARCHAR NOT NULL,
  entity_type VARCHAR NOT NULL,
  entity_id UUID NOT NULL,
  old_value JSONB,
  new_value JSONB,
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
  -- append-only log: intentionally no updated_at, a row is never mutated after insert
);
CREATE INDEX idx_audit_logs_org_id ON audit_logs(org_id);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);

-- Processing Jobs (async state machine)
CREATE TABLE processing_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tb_id UUID NOT NULL REFERENCES trial_balances(id) ON DELETE CASCADE,
  job_type VARCHAR NOT NULL CHECK (job_type IN ('parse','map','validate','statements','variance','risk','export')),
  status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','complete','failed','retrying')),
  step VARCHAR,
  progress_pct INTEGER CHECK (progress_pct >= 0 AND progress_pct <= 100),
  attempt_count INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 3,
  error_message TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_processing_jobs_tb_id ON processing_jobs(tb_id);
CREATE INDEX idx_processing_jobs_status ON processing_jobs(status);

-- Subscription Events (Stripe webhook log)
CREATE TABLE subscription_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
  stripe_event_id VARCHAR UNIQUE NOT NULL,
  event_type VARCHAR NOT NULL,
  payload JSONB NOT NULL,
  processed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
  -- append-only event log: intentionally no updated_at
);
CREATE INDEX idx_subscription_events_org ON subscription_events(org_id);
CREATE INDEX idx_subscription_events_stripe ON subscription_events(stripe_event_id);

-- Notifications
CREATE TABLE notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
  type VARCHAR NOT NULL CHECK (type IN ('processing_complete','export_ready','validation_failed','llm_unavailable','billing_alert')),
  title VARCHAR NOT NULL,
  message TEXT NOT NULL,
  is_read BOOLEAN DEFAULT FALSE,
  action_url VARCHAR,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW() -- NEW in v3.1: is_read mutates after insert, needs a timestamp
);
CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_user_read ON notifications(user_id, is_read);

-- Archived Records (WORM-style immutable snapshot, v3.2 addition)
-- Written whenever a user "deletes" a client, org, or trial balance. The action
-- sets is_deleted/deleted_at on the live row as before; this table separately
-- preserves a complete, hash-verified snapshot for the statutory retention
-- period, independent of what happens to the live row afterwards.
CREATE TABLE archived_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organisations(id),
  client_id UUID REFERENCES clients(id), -- NULL for org-level archive_reason ('org_deleted', 'subscription_cancelled') -- retrieved via GET /organisations/me/archived-records, not the client-scoped endpoint (Section 10.2)
  entity_type VARCHAR NOT NULL, -- 'trial_balance', 'financial_statement', 'export', etc.
  entity_id UUID NOT NULL,
  archive_reason VARCHAR NOT NULL, -- 'user_deleted', 'org_deleted', 'subscription_cancelled'
  archived_by_user_id UUID REFERENCES users(id),
  archived_data JSONB NOT NULL, -- complete snapshot of the record at archival time
  archive_hash VARCHAR(64) NOT NULL, -- SHA-256 of archived_data, for tamper-evidence
  retention_until DATE NOT NULL, -- archive date + 7 years (Section 12.2)
  created_at TIMESTAMPTZ DEFAULT NOW()
  -- append-only, like audit_logs and subscription_events: no updated_at
);
CREATE INDEX idx_archived_records_org ON archived_records(org_id);
CREATE INDEX idx_archived_records_entity ON archived_records(entity_type, entity_id);
CREATE INDEX idx_archived_records_retention ON archived_records(retention_until);
-- The actual export FILE (if entity_type = 'export') additionally uses S3/R2
-- Object Lock in Compliance mode for the WORM guarantee at the storage layer --
-- archived_records is the queryable, database-side record of what was archived
-- and when; Object Lock is what makes the underlying file itself undeletable.
```

#### Hard Constraint: TB Balance Trigger (v3.2, corrected)

*An earlier draft of this trigger checked NEW.validation_results->>'tb_integrity_passed' — a flat key that does not exist in this document's own validation_results shape (Section 10.3 shows checks as a JSON array of {check_name, passed, ...} objects). Against the real shape, that comparison always evaluates to NULL, the RAISE EXCEPTION never fires, and the trigger silently does nothing while appearing to be a hard legal safeguard. That version also only checked 2 of the 3 blocking checks in Section 4.2.1's table — Check 4 (Net Assets) is Error/blocks-export too, and was silently missing. Both fixed below: correct JSONB path, and all three blocking checks (tb_integrity, balance_sheet_balance, net_assets) enforced, driven by a single list rather than repeated by hand so a fourth blocking check added later can't be missed the same way.*

```sql
CREATE OR REPLACE FUNCTION enforce_tb_balance()
RETURNS TRIGGER AS $$
DECLARE
  -- Every check in Section 4.2.1 with Severity = Error / Blocks Export = Yes
  -- must appear in this array. Checks 3, 5, 6 are Warning/Info and do not block.
  blocking_checks TEXT[] := ARRAY['tb_integrity', 'balance_sheet_balance', 'net_assets'];
  check_name TEXT;
  check_failed BOOLEAN;
BEGIN
  IF NEW.status = 'complete' AND NEW.validation_results IS NOT NULL THEN

    FOREACH check_name IN ARRAY blocking_checks LOOP
      SELECT EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.validation_results->'checks') AS c
        WHERE c->>'check_name' = check_name AND (c->>'passed')::boolean = FALSE
      ) INTO check_failed;

      IF check_failed THEN
        RAISE EXCEPTION 'Cannot mark trial balance complete: % check failed.', check_name;
      END IF;
    END LOOP;

  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_enforce_tb_balance
  BEFORE UPDATE ON trial_balances
  FOR EACH ROW
  EXECUTE FUNCTION enforce_tb_balance();
```

*This is a database-level backstop behind the application-level validation in Section 4.2.1, not a replacement for it — the application should never rely on the trigger to catch what it should have caught first. Test this trigger directly against real validation_results payloads (Section 12.7 checklist), not just through the API, since a shape mismatch here is exactly the kind of bug that silently defeats it.*

### 9.2 PostgreSQL Row-Level Security (RLS)

*v3.1: this section is rewritten. v3.0 showed one working example (clients, which has a direct org_id column) and a one-line note — "similar policies for trial_balances (via client_id join)" — for every other table. That note undersold the problem: none of financial_statements, statement_line_items, variance_analyses, risk_flags, or exports have an org_id column at all. Some are two or three joins away from organisations. A "similar" policy for these tables isn't the same shape as the clients example — it needs a correlated subquery, and subqueries in RLS policies run on every row access, so they need supporting indexes or they will be slow at scale.*

#### Tables with a direct org_id column (simple policy)

```sql
-- clients, audit_logs, notifications, and archived_records (v3.2) all have org_id directly.
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
CREATE POLICY clients_org_isolation ON clients
  FOR ALL
  USING (org_id = current_setting('app.current_org_id')::UUID);
-- Repeat verbatim (swap table name) for audit_logs, notifications, and archived_records.
```

#### Tables one join from org_id (trial_balances, account_mappings)

```sql
ALTER TABLE trial_balances ENABLE ROW LEVEL SECURITY;
CREATE POLICY trial_balances_org_isolation ON trial_balances
  FOR ALL
  USING (
    client_id IN (
      SELECT id FROM clients
      WHERE org_id = current_setting('app.current_org_id')::UUID
    )
  );
-- account_mappings uses the identical pattern (it also joins via client_id).
-- Index clients.org_id (already present, Section 9.1) so this subquery is an
-- index scan, not a sequential scan, on every row check.
```

#### Tables two or three joins from org_id (financial_statements, statement_line_items, variance_analyses, risk_flags, exports)

```sql
ALTER TABLE financial_statements ENABLE ROW LEVEL SECURITY;
CREATE POLICY financial_statements_org_isolation ON financial_statements
  FOR ALL
  USING (
    tb_id IN (
      SELECT tb.id FROM trial_balances tb
      JOIN clients c ON tb.client_id = c.id
      WHERE c.org_id = current_setting('app.current_org_id')::UUID
    )
  );
-- variance_analyses and risk_flags use the identical tb_id -> trial_balances -> clients pattern.
-- exports uses the same pattern via its own tb_id column.
-- statement_line_items joins one hop further, via statement_id -> financial_statements:
ALTER TABLE statement_line_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY statement_line_items_org_isolation ON statement_line_items
  FOR ALL
  USING (
    statement_id IN (
      SELECT fs.id FROM financial_statements fs
      JOIN trial_balances tb ON fs.tb_id = tb.id
      JOIN clients c ON tb.client_id = c.id
      WHERE c.org_id = current_setting('app.current_org_id')::UUID
    )
  );
```

*Application layer must STILL filter by org_id (or client_id, joined) on every query. RLS is defence-in-depth, not a replacement for the application-layer check in Cursor AI Rules Section 8.2. Add an integration test per table verifying cross-org isolation, following the pattern in Cursor AI Rules Section 11.7 — do this for every table above, not just clients.*

---

## 10. API Specification

All endpoints except `/auth/webhook` and `/webhooks/stripe` require valid Clerk JWT in `Authorization: Bearer <token>` header. JWT claims expected: `sub` (user ID), `org_id` (organisation ID), `role`.

### Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | /auth/webhook | Clerk webhook for user/org sync |

### Organisations

| Method | Path | Description |
|--------|------|-------------|
| GET | /organisations/me | Get current user's org |
| PUT | /organisations/me | Update org settings (name, currency) |
| GET | /organisations/me/members | List org members |
| POST | /organisations/me/invites | Invite member by email |
| DELETE | /organisations/me/members/{user_id} | Remove member |

### Clients

| Method | Path | Description |
|--------|------|-------------|
| POST | /clients | Create client workspace |
| GET | /clients | List clients for org (paginated) |
| GET | /clients/{id} | Get client detail |
| PUT | /clients/{id} | Update client |
| DELETE | /clients/{id} | Soft delete client |
| GET | /clients/{id}/mappings | List all confirmed mappings for client |
| DELETE | /clients/{id}/mappings | Bulk delete mappings (for reset) |

### Trial Balances

| Method | Path | Description |
|--------|------|-------------|
| POST | /trial-balances/upload | Upload TB file, return job_id |
| GET | /trial-balances | List TBs for client (paginated) |
| GET | /trial-balances/{id} | Get TB detail + status |
| DELETE | /trial-balances/{id} | Delete TB and all derived data |
| GET | /trial-balances/{id}/status | Poll processing status |
| GET | /trial-balances/{id}/mapping | Get suggested mappings |
| POST | /trial-balances/{id}/mapping/confirm | Confirm mappings, trigger validation |
| PUT | /trial-balances/{id}/mapping/{mapping_id} | Update single mapping |
| GET | /trial-balances/{id}/validation | Get validation results |
| POST | /trial-balances/{id}/statements | Generate SOPL/SOFP/SOCIE |
| GET | /trial-balances/{id}/statements | Get generated statements |
| PUT | /trial-balances/{id}/statements/{statement_type}/lines/{line_id} | Override line item amount |
| POST | /trial-balances/{id}/variance | Generate variance analysis |
| GET | /trial-balances/{id}/variance | Get variance with commentary |
| PUT | /variance-analyses/{id}/commentary/{line_item_code} | Update commentary text |
| POST | /trial-balances/{id}/risk | Generate risk flags |
| GET | /trial-balances/{id}/risk | Get risk heatmap |
| POST | /trial-balances/{id}/export | Trigger export (xlsx/csv/pdf) |
| GET | /exports/{id} | Get export status |
| GET | /exports/{id}/download | Download exported file (signed URL) |

### Commentary Feedback

| Method | Path | Description |
|--------|------|-------------|
| POST | /commentary/feedback | Submit thumbs up/down + correction |

### Archived Records (v3.2 — satisfies the Section 12.2 audit-retrieval requirement)

| Method | Path | Description |
|--------|------|-------------|
| GET | /clients/{id}/archived-records | List client-level archived records (archive_reason = 'user_deleted'). Query params: entity_type, period_end (exact or range). Admin+ role required. |
| GET | /organisations/me/archived-records | List org-level archived records (archive_reason = 'org_deleted' or 'subscription_cancelled') — these rows have client_id = NULL and are invisible to the client-scoped endpoint above, so this is the only way to retrieve them. Query params: entity_type, archive_reason. Owner role required. |
| GET | /archived-records/{id} | Get one archived record regardless of whether it's client- or org-scoped: full archived_data snapshot, archive_hash, retention_until. Re-computes SHA-256 of archived_data server-side and returns a hash_verified boolean, so the response itself proves the snapshot hasn't been tampered with since archival. Admin+ role required. |

### Webhooks

| Method | Path | Description |
|--------|------|-------------|
| POST | /webhooks/stripe | Stripe subscription event webhook |

### Notifications

| Method | Path | Description |
|--------|------|-------------|
| GET | /notifications | List notifications for user |
| PUT | /notifications/{id}/read | Mark notification as read |
| PUT | /notifications/read-all | Mark all as read |

### 10.3 Request/Response Examples

#### POST /trial-balances/upload — Request

```json
{
  "client_id": "550e8400-e29b-41d4-a716-446655440000",
  "period_end": "2026-07-31",
  "file": "<multipart/form-data>",
  "currency": "GBP"
}
```

Response (202 Accepted). If a TB already exists for this client_id + period_end, this returns 409 Conflict instead (Section 9.1 UNIQUE constraint, v3.1):

```json
{
  "tb_id": "660e8400-e29b-41d4-a716-446655440001",
  "job_id": "770e8400-e29b-41d4-a716-446655440002",
  "status": "pending",
  "message": "Upload accepted. Processing will begin shortly."
}
```

#### GET /trial-balances/{id}/status — Response

```json
{
  "tb_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "analysing",
  "progress_pct": 85,
  "current_step": "Generating variance commentary",
  "jobs": [
    {"job_type": "parse", "status": "complete", "completed_at": "2026-08-29T10:00:00Z"},
    {"job_type": "map", "status": "complete", "completed_at": "2026-08-29T10:00:15Z"},
    {"job_type": "validate", "status": "complete", "completed_at": "2026-08-29T10:00:30Z"},
    {"job_type": "statements", "status": "complete", "completed_at": "2026-08-29T10:01:00Z"},
    {"job_type": "variance", "status": "running", "started_at": "2026-08-29T10:01:05Z"},
    {"job_type": "risk", "status": "pending"}
  ]
}
```

#### GET /trial-balances/{id}/mapping — Response

```json
{
  "tb_id": "660e8400-e29b-41d4-a716-446655440001",
  "mapping_rate": 0.92,
  "unmapped_count": 3,
  "mappings": [
    {
      "id": "880e8400-e29b-41d4-a716-446655440003",
      "source_code": "4100",
      "source_name": "Sales - Online",
      "suggested_canonical_line": "revenue",
      "confidence": 0.95,
      "method": "exact",
      "is_confirmed": false,
      "is_ignored": false
    }
  ]
}
```

#### GET /trial-balances/{id}/validation — Response

```json
{
  "tb_id": "660e8400-e29b-41d4-a716-446655440001",
  "all_passed": false,
  "can_generate_statements": false,
  "checks": [
    {
      "check_name": "tb_integrity",
      "passed": false,
      "severity": "error",
      "message": "Total debits (125,000.00) do not equal total credits (125,050.00). Difference: 50.00",
      "details": {"total_debits": "125000.00", "total_credits": "125050.00", "difference": "50.00"}
    },
    {
      "check_name": "balance_sheet_balance",
      "passed": true,
      "severity": "error",
      "message": "Balance sheet balances within tolerance."
    }
  ]
}
```

#### GET /trial-balances/{id}/variance — Response

```json
{
  "tb_id": "660e8400-e29b-41d4-a716-446655440001",
  "prior_tb_id": "550e8400-e29b-41d4-a716-446655440000",
  "materiality_threshold_pct": 10.0,
  "materiality_threshold_abs": "1000.00",
  "items": [
    {
      "line_item_code": "revenue",
      "line_item_name": "Revenue",
      "current_amount": "250000.00",
      "prior_amount": "210000.00",
      "variance_amount": "40000.00",
      "variance_pct": "19.05",
      "direction": "increase",
      "is_material": true,
      "commentary": {
        "text": "Revenue has increased significantly compared to the prior period, driven by strong online sales performance.",
        "is_ai_generated": true,
        "is_edited": false,
        "reasoning": "The revenue line showed a material increase of approximately 19%, which is above the 10% threshold.",
        "confidence": "high"
      }
    }
  ]
}
```

---

## 11. UI Specification

### 11.1 Route Map

| Route | Purpose | Auth |
|-------|---------|------|
| / | Landing/marketing page | Public |
| /onboarding | Org creation, invite team, add first client | Auth required |
| /clients | Client list with upload history, status badges | Auth required |
| /clients/[id] | Client detail: all periods, TBs, statements, team access | Auth required |
| /upload | Drag-drop upload with column mapping fallback, currency selector | Auth required |
| /mapping/[tb_id] | Mapping review table with inline edit, confidence badges, bulk actions | Auth required |
| /dashboard/[tb_id] | Main review dashboard with tabs: SOPL / SOFP / SOCIE / Variance / Risk / Export | Auth required |
| /dashboard/[tb_id]/sopl | Interactive SOPL with drill-down to source TB rows | Auth required |
| /dashboard/[tb_id]/variance | Variance table with AI commentary cards, thumbs up/down, inline edit | Auth required |
| /dashboard/[tb_id]/risk | Risk heatmap with severity colors, explanations, affected accounts | Auth required |
| /dashboard/[tb_id]/export | Export options: Excel (sheets listed), PDF, CSV | Auth required |
| /notifications | Notification centre — list, mark read/unread (NEW in v3.1, closes the gap where the API existed with no route) | Auth required |
| /settings/org | Organisation settings: members, roles, billing, subscription | Auth required (Admin+) |
| /settings/clients | Client management, mapping history, bulk import | Auth required |
| /settings/account | Personal account settings, password, 2FA | Auth required |

### 11.2 Key UI Components

#### Upload Page

- Drag-drop zone with file type icons (Excel, CSV)
- Progress bar during upload
- Column mapping fallback modal (if auto-detection confidence < 0.80)
- Currency selector dropdown (default: client functional currency)
- File info card: size, row count, detected columns
- "Upload and Parse" button → redirects to /mapping/[tb_id]

#### Mapping Page

- Summary header: "X of Y accounts mapped (Z% confidence)"
- Filter bar: search by code/name, filter by confidence, filter by method
- Virtualized table (react-window) for large TBs
- Unmapped accounts section (pinned, red badge)
- Bulk action bar: "Accept All High Confidence", "Apply Similar", "Reset"
- "Remember for [Client]" toggle (default: ON for confirmed mappings)
- "Generate Statements" button (disabled if <50% mapped)

#### Dashboard

- Tab navigation: SOPL | SOFP | SOCIE | Variance | Risk | Export
- Statement view: hierarchical line items, subtotals bold, drill-down on click
- Variance view: sortable table, commentary cards with edit pencil, thumbs up/down
- Risk view: severity color coding (warning = amber, critical = red), expandable rows
- Export view: format cards, option toggles, "Generate" button
- Global actions: "Download All", "Share" (future), "Print"

---

## 12. Security, Compliance & Irish Legal Requirements

### 12.1 Data Protection (UK & Irish GDPR)

**Lawful Basis:** Contractual necessity (providing the service) + Legitimate interest (improving AI accuracy via feedback, with opt-out).

**Data Minimisation:**

- Store only TB summary data (account codes, names, balances). No transaction-level detail.
- Do not store raw uploaded files longer than 90 days post-processing.
- Anonymise feedback data for model improvement.

**User Rights:**

- Right to access: export all data via /settings/org/data-export
- Right to erasure (limited): PII (names, emails) deleted from users on request. Financial data cannot be erased on request — it's retained per the schedule in Section 12.2, since Companies Act / Revenue obligations override an erasure request. The response to an erasure request: (a) delete PII from users, (b) anonymise clients.name to "[Redacted Client]", (c) retain financial data in archived_records with its retention_until date intact.
- Right to portability: JSON export of all client data

**Technical Measures:**

- **Encryption at rest:** AES-256-GCM for PostgreSQL (AWS RDS encryption or provider equivalent). AES-256 for S3/R2 object storage.
- **Encryption in transit:** TLS 1.3 minimum for all API endpoints. No HTTP in production. HSTS header, 1-year max-age.
- **EU data residency:** All primary data (database AND file storage — not just the database) hosted in an EU region, e.g. AWS eu-west-1 (Dublin) or an equivalent EU PostgreSQL/object-storage provider. Cross-region replication (e.g. to eu-west-2 London) is permitted for disaster-recovery purposes only, not as a primary store.
- **Access logs:** All data access logged to audit_logs.
- **Breach notification:** 72-hour internal detection-to-decision process, DPC notification within 72 hours of discovery, user notification within 7 days if high risk. Documented in docs/runbooks/data-breach-response.md.

**Records:**

- Privacy policy (required before launch)
- Data Processing Agreement (DPA) for B2B customers — see Section 12.3
- Cookie policy (minimal cookies, essential only)

### 12.2 Retention & Immutable Archival (Companies Act 2014 / Revenue Commissioners)

*Statutory basis: Companies Act 2014 §285 (Ireland) requires accounting records to be preserved for 6 years after the financial year they relate to; Taxes Consolidation Act 1997 §886 sets the same 6-year minimum for tax records. UK practice converges on the same figure (Companies Act 2006 technically requires only 3 years for private companies, but UK tax law requires 6). 6 years is the statutory floor in both markets — nothing in either statute requires 7.*

**This document's policy is 7 years: the 6-year statutory minimum plus a 1-year engineering buffer, adopted deliberately as a safety margin against edge cases (a financial year-end that doesn't align cleanly to a calendar boundary, a late audit query, an ambiguous "from the end of the accounting period" date). This is a risk-management choice, not a restatement of the law — stated explicitly here so it doesn't get miscited elsewhere as a legal requirement.**

| Data Type | Retention Period | Storage |
|-----------|------------------|---------|
| Trial balances (raw upload) | 90 days post-processing | S3/R2, standard |
| Statement data (financial_statements, statement_line_items) | 7 years (6yr statutory + 1yr buffer) | PostgreSQL — cheap, no file-storage cost |
| Account mappings | 7 years (client continuity + audit trail) | PostgreSQL |
| Audit logs | 7 years (legal liability record) | PostgreSQL, append-only |
| Generated export files (Excel/PDF/CSV) | 30 days, then deleted; regenerate on demand from statement data | S3/R2 — this is the control that bounds storage cost, see Section 12.6 |
| Archived records (post-deletion snapshot) | 7 years from archive date | S3/R2 with Object Lock (Compliance mode) — WORM, cannot be deleted or overwritten by any user including root account holders |
| User PII (names, emails) | Until account deletion + 30 days | PostgreSQL |

**Immutable archival:** when a user "deletes" a client, org, or trial balance, the record is never hard-deleted. The action sets is_deleted/archived_at and a snapshot is written to the archived_records table (Section 9.1) with a SHA-256 hash of the snapshot, so the exact state of any record at any point in its life is cryptographically verifiable — useful in a Revenue audit or a dispute over what FinDraft actually showed a user on a given date. Any archived record must be retrievable by org_id + client_id + period_end — GET /clients/{id}/archived-records and GET /archived-records/{id} (Section 10.2, v3.2) are what actually serve this; the requirement existed in earlier drafts with no endpoint behind it.

### 12.3 Data Processing Agreements & Sub-Processors

Every client organisation must be provided with a Data Processing Agreement (DPA) before their data is processed. The DPA must state: FinDraft acts as Processor, the client is Controller, sub-processors are listed and kept current, and data is not used for model training without explicit opt-in.

| Sub-Processor | Role | Location | SCC + TIA Required? |
|---------------|------|----------|---------------------|
| AWS (or equivalent) | Infrastructure | EU (Dublin) | No — EU-to-EU |
| OpenAI | AI commentary | US | Yes — Standard Contractual Clauses + Transfer Impact Assessment |
| Stripe | Payments | US | Yes — SCC + TIA |
| Clerk | Authentication | US | Yes — SCC + TIA |
| Resend | Email | US | Yes — SCC + TIA |

*A Transfer Impact Assessment (TIA) must be completed and documented for each US-based sub-processor before launch, per the post-Schrems II standard. This is a one-time documentation task per sub-processor, not a per-transaction check.*

### 12.4 PSD2 / Open Banking (Post-MVP — Not in Scope)

If FinDraft ever pulls live bank feeds or transaction histories directly from a bank (rather than the user uploading their own export), that connection cannot be built as scraping — it must route through either a regulated Account Information Service Provider (AISP) holding Central Bank of Ireland authorisation, or a licensed aggregator (Plaid EU, Yapily, TrueLayer) that already holds that licence.

*MVP status: not applicable. FinDraft's only input is a file the user uploads themselves (Section 4.1) — there is no bank connection anywhere in this specification, MVP or Post-MVP. This becomes a real requirement only if direct API integrations (Section 16, Month 6, Xero/QuickBooks/Sage) are ever extended to include live bank feeds specifically — at that point, legal counsel must review AISP licensing before building it, not after.*

### 12.5 Application Security

| Control | Implementation |
|---------|----------------|
| Authentication | Clerk JWT, 15-minute expiry, refresh tokens |
| Authorisation | Role-based access control (RBAC) + PostgreSQL RLS |
| Input Validation | Pydantic v2 on all API inputs. Zod on frontend forms. |
| File Upload | Type whitelist (.xlsx, .csv), size limit (50MB), ClamAV scan, random UUID filename |
| SQL Injection | SQLAlchemy ORM exclusively. No raw SQL with string interpolation. |
| XSS | React auto-escaping. CSP headers. No dangerouslySetInnerHTML. |
| CSRF | SameSite cookies. Clerk handles CSRF for auth endpoints. |
| Rate Limiting | 100 req/min per user. 10 uploads/hour per org (Free). 50 uploads/hour (Paid). |
| Secrets Management | Pydantic Settings with .env. No secrets in code. Quarterly rotation. |
| CORS | Frontend origin only. No wildcards in production. |
| Dependency Scanning | Dependabot + pip-audit in CI/CD. |

### 12.6 Audit & Accountability

- All financial data mutations logged to audit_logs (who, what, when, from what IP).
- Generated export files (the PDF/Excel/CSV) retained 30 days, then deleted; regenerated on demand from the underlying statement data, which is retained 7 years per Section 12.2. This split — not "keep every export file for 7 years" — is what actually bounds S3/R2 storage cost; see Section 12.2's table for the full picture.
- Statement versions not stored in MVP (Post-MVP: version history).
- Admin dashboard (future) to view audit logs for compliance checks.
- The TB-balance database trigger (Section 9.1) is a hard, database-level backstop — not merely a UX validation message — preventing a trial balance from ever being marked complete while Check 1 (TB Integrity) or Check 2 (Balance Sheet Balance) is failing.

### 12.7 Compliance Checklist (Pre-Launch)

- Draft and publish Privacy Policy (GDPR-compliant, referencing both UK and Irish law)
- Draft and publish Data Processing Agreement (DPA) template for B2B clients
- Execute Standard Contractual Clauses (SCCs) with all US sub-processors (Section 12.3)
- Complete Transfer Impact Assessments (TIAs) for OpenAI, Stripe, Clerk, Resend
- Configure S3/R2 Object Lock (Compliance mode) for the archived_records / WORM storage path
- Configure database and object storage encryption (AES-256) in an EU region
- Implement and test the corrected enforce_tb_balance trigger (Section 9.1) against real validation_results payloads, not just the happy path
- Configure TLS 1.3 on all endpoints; confirm HTTP is disabled, not just unadvertised
- Add HSTS headers (1-year max-age)
- Document the data breach response procedure (72h internal → DPC, 7d → affected client)
- Add a limitation-of-liability / "drafting tool, not a substitute for professional judgment" clause to the Terms of Service — this is a legal drafting task, not an engineering one, and doesn't block the build (see conversation notes on this distinction)
- Obtain professional indemnity insurance (this is the actual backstop for the liability scenario in Companies Act §281–285 — no amount of validation logic makes that risk zero)

*Deliberately not on this list: registering with the Irish DPC. That requirement was abolished when GDPR took effect in May 2018 — there is no register to join, no number to obtain, and no fee to pay. If this appears on a checklist you're handed by someone else, it's outdated advice from the pre-2018 Data Protection Acts regime.*

---

## 13. Pricing & Packaging

### 13.1 Feature-to-Tier Matrix

| Feature | Free | Starter (£49/mo) | Pro (£149/mo) | Scale (£349/mo) |
|---------|------|------------------|---------------|-----------------|
| Clients | 1 | 5 | 25 | Unlimited |
| SOPL/SOFP/SOCIE | Yes | Yes | Yes | Yes |
| CSV Export | Yes | Yes | Yes | Yes |
| Excel Export | Watermarked | No watermark | No watermark | No watermark + custom templates |
| PDF Export | Watermarked | No watermark | No watermark | White-label (no FinDraft branding) |
| Variance Analysis (calculated) | Yes | Yes | Yes | Yes |
| Risk Heatmap (2 rules) | No | Yes | Yes | Yes |
| AI Commentary (variances) | No | No | Yes | Yes |
| AI Business Health Summary | No | No | Yes | Yes |
| Evidence Graph | Basic | Basic | Advanced | Advanced |
| Priority Support | Email only | Email only | Priority | Dedicated |
| API Access | No | No | No | Yes |
| Team Members | 1 | 3 | 10 | Unlimited |

### 13.2 Billing

- Monthly billing default. Annual billing: 2 months free (17% discount).
- 14-day free trial on Starter/Pro/Scale (no credit card required).
- Stripe Checkout for self-serve. Stripe Customer Portal for plan changes.
- Prorated upgrades. Immediate downgrades (no refunds for current period).
- Over-limit behaviour: soft limit (warn at 80% of client cap). Hard block at 100% (upload disabled until upgrade or archive).

---

## 14. Success Metrics (12-Week MVP)

### Phase 1: Validate Demand (Weeks 1–4)

- Week 2: 25 email signups on landing page. 5 say they'd pay.
- Week 4: 50 email signups. 3 organisations created via concierge onboarding. 1 paying customer (£49+) from manual onboarding.
- Gate: If <25 signups by Week 4, pause build. Fix positioning and landing page.

### Phase 2: Build Core Engine (Weeks 5–8)

- Week 6: TB parser + mapper + validation working end-to-end in staging.
- Week 7: Statement builder + variance analysis working. AI commentary in alpha.
- Week 8: Full async pipeline working. 2 additional paying customers from concierge.
- Gate: If core engine not working by Week 8, cut AI commentary from MVP. Ship deterministic features only.

### Phase 3: Productise & Self-Serve (Weeks 9–12)

- Week 10: Self-serve upload → mapping → statements → export works without manual intervention.
- Week 11: Stripe self-serve checkout live. Onboarding flow polished.
- Week 12: 5 paying customers, £245 MRR. First unassisted signup + payment.
- Gate: If no unassisted signup by Week 12, extend to Week 14. Focus on UX friction removal.

### Post-MVP Targets

- Month 3: 20 paying customers, £980 MRR. <5% monthly churn.
- Month 6: 50 paying customers, £4,900 MRR. Evidence graph v2 shipped. Risk rules expanded to 7.
- Month 12: 150 paying customers, £20,000+ MRR. API access live. First enterprise (£349) customer.

---

## 15. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Mapping accuracy poor | Medium | High | Hybrid approach + user review + per-client memory. Unmapped never auto-assigned. Target: >90% auto-map rate for recurring clients. |
| LLM hallucination in commentary | Medium | Critical | Structured JSON only. Temp 0.1–0.2. No numbers in prompts. User review mandatory. Thumbs down logged. |
| Math errors destroy trust | Low | Critical | Decimal module only. €0.01 tolerance. 5 validation checks + 1 status flag. Evidence graph. Extensive unit tests. |
| Solo founder burnout | High | High | 12-week realistic timeline. Scope lock enforced. No feature creep without spec update. Async architecture. |
| Free tier abuse | Medium | Medium | 1 client limit enforced at DB. Watermark on PDF. Rate limiting. No API on Free. |
| Data breach / GDPR fine | Low | Critical | Encryption at rest/transit. EU data residency (Section 12.1). RLS (join-based policies, Section 9.2). Immutable audit logs and archived_records (Section 12.2). DPA + sub-processor SCCs/TIAs (Section 12.3). Privacy policy. Breach response plan. |
| Stripe billing issues | Medium | Medium | Webhook event sourcing. Graceful degradation if Stripe down. Clear error messages for payment failures. |
| Competitor launches similar | Medium | Medium | Speed to market. Focus on "any Excel TB" parsing + evidence graph. Build brand in UK/Ireland first. |
| OpenAI API pricing changes | Medium | Medium | Cache commentary (1 hour). Use GPT-4o-mini for non-critical tasks. Monitor token usage per org. Cost alerts. |
| Large TB performance issues | Medium | Medium | Chunked parsing. Virtualized tables. Background processing. Connection pooling. Query timeouts. |

---

## 16. Post-MVP Roadmap (Not in Scope)

| Month | Feature |
|-------|---------|
| Month 3 | Cash flow forecasting (3-month forward projection from historical TBs) |
| Month 4 | Scenario modelling (revenue ±X%, margin ±Y% sliders with real-time impact) |
| Month 4 | Budget upload + budget-vs-actual variance |
| Month 5 | Transaction-level GL analysis (monthly spend/revenue breakdown) |
| Month 6 | Direct API integrations (Xero, QuickBooks, Sage) |
| Month 6 | Full risk rules engine (7 rules: debtor ageing, related-party, going concern, etc.) |
| Month 9 | Industry benchmarking (external data integration) |
| Month 12 | Predictive advisory layer (macroeconomic context, "what should the business do") |

---

## 17. Appendices

### Appendix A: Canonical Account Lines

```python
# From shared/canonical_accounts.py
CANONICAL_LINES = [
  "revenue", "cost_of_sales", "gross_profit",  # calculated
  "operating_expenses", "depreciation", "amortisation", "operating_profit",  # calculated
  "interest_income", "interest_expense", "profit_before_tax",  # calculated
  "tax", "net_profit",  # calculated
  "property_plant_equipment", "intangible_assets", "investments", "inventory",
  "trade_receivables", "prepayments", "accrued_income", "cash", "total_assets",  # calculated
  "trade_payables", "provisions", "accruals", "deferred_income",
  "taxes_payable", "social_security_payable", "loans", "total_liabilities",  # calculated
  "share_capital", "share_premium", "retained_earnings", "revaluation_reserve",
  "dividends", "total_equity",  # calculated
  "unmapped",
]
```

### Appendix B: Materiality Rules

*v3.1: corrected. v3.0 stated a tier-differentiated default (Pro/Scale: 5% or 500) that doesn't exist anywhere in the schema or onboarding flow — clients.materiality_threshold_pct/abs (Section 9.1) has exactly one default regardless of tier. The rule and the one real default are shown below; if tier-differentiated defaults are wanted, that's a real feature to design and schedule, not something to assert here as already true.*

```python
# Per-client materiality (stored in clients table)
def is_material(variance_amount: Decimal, variance_pct: Decimal,
                threshold_abs: Decimal, threshold_pct: Decimal) -> bool:
    return abs(variance_amount) >= threshold_abs or abs(variance_pct) >= threshold_pct

# Default threshold, all tiers: 10% or 1,000 functional currency units.
# Editable per client, on any tier, via PUT /clients/{id}.
```

### Appendix C: Code Range Heuristics (UK Chart of Accounts)

| Range | Category |
|-------|----------|
| 1000–1999 | Assets (PPE, inventory, receivables, cash) |
| 2000–2999 | Liabilities (payables, accruals, loans) |
| 3000–3999 | Equity (share capital, retained earnings) |
| 4000–4999 | Revenue |
| 5000–5999 | Cost of Sales |
| 6000–6999 | Operating Expenses |
| 7000–7999 | Depreciation / Amortisation |
| 8000–8999 | Interest / Tax |
| 9000–9999 | Suspense / Unmapped |

*Note: These are heuristics only. Exact mapping depends on client's actual chart of accounts. Always confirmed by user.*

### Appendix D: Risk Rule Detail

**Rule 1: Negative Cash/Bank**

- Trigger: Any account mapped to cash with net_balance < 0
- Severity: warning
- Explanation: "A cash or bank account shows a negative balance. This may indicate an overdraft, uncleared items, or a data entry error. Verify with bank statements."

**Rule 2: Unusual Variance**

- Trigger: See Section 4.3 for tiered logic
- Severity: warning
- Explanation Template: "[Line item] has varied by [X]% compared to the prior period, which is unusual based on [Y] months of historical data. Review for one-off transactions or data errors."

---

**END OF SPECIFICATION**

*This document is a draft for review. Locking requires founder sign-off and version bump to 3.2-LOCKED.*
