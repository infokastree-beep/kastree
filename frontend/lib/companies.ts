import { apiFetch } from "@/lib/api";
import {
  DEFAULT_MATERIALITY_ABS,
  DEFAULT_MATERIALITY_PCT,
  type CompanyEntityFormValues,
} from "@/lib/company-form";
import type {
  CompanyCreateRequest,
  CompanyUpdateRequest,
  ICompany,
} from "@/types";

type TokenGetter = () => Promise<string | null>;

export async function createCompanyEntity(
  clientId: string,
  values: CompanyEntityFormValues,
  getToken: TokenGetter,
): Promise<ICompany> {
  const body: CompanyCreateRequest = {
    name: values.name,
    functional_currency: values.functionalCurrency,
  };
  const trimmedCompany = values.companyNumber.trim();
  const trimmedIndustry = values.industry.trim();
  if (trimmedCompany) {
    body.company_number = trimmedCompany;
  }
  if (trimmedIndustry) {
    body.industry = trimmedIndustry;
  }

  const company = await apiFetch<ICompany>(`/clients/${clientId}/companies`, {
    method: "POST",
    getToken,
    body: JSON.stringify(body),
  });

  const pctChanged = values.materialityPct !== DEFAULT_MATERIALITY_PCT;
  const absChanged = values.materialityAbs !== DEFAULT_MATERIALITY_ABS;
  if (!pctChanged && !absChanged) {
    return company;
  }

  const update: CompanyUpdateRequest = {};
  if (pctChanged) {
    update.materiality_threshold_pct = values.materialityPct;
  }
  if (absChanged) {
    update.materiality_threshold_abs = values.materialityAbs;
  }

  return apiFetch<ICompany>(`/companies/${company.id}`, {
    method: "PUT",
    getToken,
    body: JSON.stringify(update),
  });
}
