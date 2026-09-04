/** Shared TypeScript types for the core upload → mapping → dashboard loop. */

export interface IClient {
  id: string;
  org_id: string;
  name: string;
  is_deleted: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClientCreateRequest {
  name: string;
}

export interface ClientListResponse {
  items: IClient[];
  total: number;
  limit: number;
  offset: number;
}

export interface ICompany {
  id: string;
  client_id: string;
  name: string;
  company_number: string | null;
  industry: string | null;
  functional_currency: string;
  materiality_threshold_pct: string;
  materiality_threshold_abs: string;
  is_deleted: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompanyCreateRequest {
  name: string;
  company_number?: string | null;
  industry?: string | null;
  functional_currency?: string;
}

export interface CompanyUpdateRequest {
  materiality_threshold_pct?: string;
  materiality_threshold_abs?: string;
}

export interface CompanyListResponse {
  client_id: string;
  items: ICompany[];
  total: number;
}

export interface TrialBalanceListItem {
  id: string;
  company_id: string;
  period_end: string;
  status: string;
  created_at: string;
}

export interface TrialBalanceListResponse {
  items: TrialBalanceListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface UploadAcceptedResponse {
  tb_id: string;
  job_id: string;
  status: "pending";
  message: string;
}

export interface StatusResponse {
  tb_id: string;
  status: string;
  progress_pct: number;
  current_step: string | null;
  error_message: string | null;
  jobs: Array<{
    job_type: string;
    status: string;
    started_at: string | null;
    completed_at: string | null;
  }>;
}

export interface MappingItem {
  id: string;
  source_code: string | null;
  source_name: string;
  suggested_canonical_line: string;
  confidence: number | null;
  method: string;
  is_confirmed: boolean;
  is_ignored: boolean;
}

export interface MappingResponse {
  tb_id: string;
  mapping_rate: number;
  unmapped_count: number;
  mappings: MappingItem[];
}

export interface MappingConfirmItem {
  id: string;
  canonical_line: string;
  is_confirmed: boolean;
  is_ignored: boolean;
}

export interface MappingConfirmResponse {
  tb_id: string;
  confirmed_count: number;
  validation_job_id: string;
  status: string;
}

export interface StatementLine {
  id: string;
  line_item_code: string;
  line_item_name: string;
  amount: string;
  is_subtotal: boolean;
  display_order: number;
  source_account_ids: string[];
}

export interface StatementBlock {
  statement_type: "SOPL" | "SOFP" | "SOCIE";
  generated_at: string;
  lines: StatementLine[];
}

export interface StatementsResponse {
  tb_id: string;
  functional_currency: string;
  statements: StatementBlock[];
}

export type VarianceDirection = "increase" | "decrease" | "new" | "removed";

export interface VarianceCommentary {
  text: string;
  reasoning?: string | null;
  confidence?: "high" | "medium" | "low" | null;
  is_edited?: boolean;
}

export interface VarianceItem {
  line_item_code: string;
  line_item_name: string;
  current_amount: string;
  prior_amount: string;
  variance_amount: string;
  variance_pct: string | null;
  direction: VarianceDirection;
  is_material: boolean;
  commentary?: VarianceCommentary | null;
}

export interface VarianceResponse {
  tb_id: string;
  prior_tb_id: string | null;
  variance_available: boolean;
  message: string | null;
  materiality_threshold_pct: number | null;
  materiality_threshold_abs: string | null;
  items: VarianceItem[];
}

export type RiskSeverity = "warning" | "critical";

export interface RiskAffectedAccount {
  account_code: string;
  account_name: string;
  net_balance: string;
}

export interface RiskFlag {
  id: string;
  rule_name: string;
  severity: RiskSeverity;
  description: string;
  affected_accounts: RiskAffectedAccount[] | null;
  recommended_action: string | null;
}

export interface RiskFlagsResponse {
  tb_id: string;
  flags: RiskFlag[];
  unusual_variance_history_months: number;
}

export type ExportFormat = "xlsx" | "csv" | "pdf";
export type ExportStatus = "pending" | "processing" | "complete" | "failed";

export interface ExportAcceptedResponse {
  export_id: string;
  tb_id: string;
  status: "pending";
  message: string;
}

export interface ExportStatusResponse {
  id: string;
  tb_id: string;
  format: ExportFormat;
  status: ExportStatus;
  file_url: string | null;
  error_message: string | null;
}
