import { apiFetch } from "@/lib/api";
import type { CompanyEntityFormValues } from "@/lib/company-form";
import type {
  CompanyCreateRequest,
  CompanyUpdateRequest,
  ICompany,
} from "@/types";

type TokenGetter = () => Promise<string | null>;

/**
 * Create a company under a client group.
 * Materiality is not collected at create time — DB defaults (10% / 1000)
 * apply silently. Edit thresholds later via updateCompanyMateriality.
 */
export async function createCompanyEntity(
  clientId: string,
  values: CompanyEntityFormValues,
  getToken: TokenGetter,
): Promise<ICompany> {
  const body: CompanyCreateRequest = {
    name: values.name,
    functional_currency: values.functionalCurrency,
    company_type: values.companyType,
  };
  const trimmedCompany = values.companyNumber.trim();
  const trimmedIndustry = values.industry.trim();
  if (trimmedCompany) {
    body.company_number = trimmedCompany;
  }
  if (trimmedIndustry) {
    body.industry = trimmedIndustry;
  }

  return apiFetch<ICompany>(`/clients/${clientId}/companies`, {
    method: "POST",
    getToken,
    body: JSON.stringify(body),
  });
}

/** Update materiality thresholds on an existing company (manual entry). */
export async function updateCompanyMateriality(
  companyId: string,
  values: { materialityPct: string; materialityAbs: string },
  getToken: TokenGetter,
): Promise<ICompany> {
  const update: CompanyUpdateRequest = {
    materiality_threshold_pct: values.materialityPct,
    materiality_threshold_abs: values.materialityAbs,
  };
  return apiFetch<ICompany>(`/companies/${companyId}`, {
    method: "PUT",
    getToken,
    body: JSON.stringify(update),
  });
}

/**
 * Update company identity / classification fields (name, currency, type, etc.).
 * Does not touch materiality thresholds — use updateCompanyMateriality for those.
 */
export async function updateCompanyEntity(
  companyId: string,
  values: CompanyEntityFormValues,
  getToken: TokenGetter,
): Promise<ICompany> {
  const update: CompanyUpdateRequest = {
    name: values.name,
    functional_currency: values.functionalCurrency,
    company_type: values.companyType,
    company_number: values.companyNumber.trim() ? values.companyNumber.trim() : null,
    industry: values.industry.trim() ? values.industry.trim() : null,
  };
  return apiFetch<ICompany>(`/companies/${companyId}`, {
    method: "PUT",
    getToken,
    body: JSON.stringify(update),
  });
}

/** Soft-delete a company (archived_records snapshot; children not cascaded). */
export async function deleteCompanyEntity(
  companyId: string,
  getToken: TokenGetter,
): Promise<ICompany> {
  return apiFetch<ICompany>(`/companies/${companyId}`, {
    method: "DELETE",
    getToken,
  });
}
