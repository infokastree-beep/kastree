/** Application constants shared by the core-loop UI. */

export const APP_NAME = "FinDraft";

/** Where Clerk sends a user after sign-in / sign-up. Must be a dashboard route. */
export const POST_AUTH_PATH = "/upload";

/** Same disclaimer the exporter stamps on every pack (backend/app/services/exporter.py). */
export const DISCLAIMER_TEXT =
  "Prepared for internal review and analysis. Not a statutory financial statement and not intended for regulatory filing.";

/**
 * Appendix A mappable canonical lines (+ unmapped) — matches
 * MAPPING_TIE_BREAKER_CANONICAL_LINES in backend/app/services/llm.py (29 lines).
 */
export const CANONICAL_LINES: readonly string[] = [
  "revenue",
  "cost_of_sales",
  "operating_expenses",
  "depreciation",
  "amortisation",
  "interest_income",
  "interest_expense",
  "tax",
  "property_plant_equipment",
  "intangible_assets",
  "investments",
  "inventory",
  "trade_receivables",
  "prepayments",
  "accrued_income",
  "cash",
  "trade_payables",
  "provisions",
  "accruals",
  "deferred_income",
  "taxes_payable",
  "social_security_payable",
  "loans",
  "share_capital",
  "share_premium",
  "retained_earnings",
  "revaluation_reserve",
  "dividends",
  "unmapped",
] as const;

export const ACCEPTED_UPLOAD_EXTENSIONS = [".xlsx", ".csv"] as const;
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

/** Supported functional currencies for client + upload forms. */
export const FUNCTIONAL_CURRENCIES = ["GBP", "EUR", "USD"] as const;
export type FunctionalCurrency = (typeof FUNCTIONAL_CURRENCIES)[number];
