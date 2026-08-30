/** Shared TypeScript types for the core upload → mapping → dashboard loop. */

export interface IClient {
  id: string;
  name: string;
  functional_currency: string;
}

export interface ClientListResponse {
  items: IClient[];
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
  statements: StatementBlock[];
}
