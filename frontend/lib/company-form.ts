/** Silent defaults applied by the DB when creating a company (not shown on create form). */
export const DEFAULT_MATERIALITY_PCT = "10.00";
export const DEFAULT_MATERIALITY_ABS = "1000.00";

export type CompanyEntityFormValues = {
  name: string;
  functionalCurrency: string;
  companyNumber: string;
  industry: string;
  companyType: "trading" | "holding";
  acknowledgeCurrencyChange?: boolean;
};

/** Values the edit form shows before the user changes them. */
export type CompanyEntityInitialValues = {
  name: string;
  functionalCurrency: string;
  companyNumber: string;
  industry: string;
  companyType: CompanyEntityFormValues["companyType"];
};

export function editCompanyInitialValues(company: {
  name: string;
  functional_currency: string;
  company_number?: string | null;
  industry?: string | null;
  company_type: CompanyEntityInitialValues["companyType"];
}): CompanyEntityInitialValues {
  return {
    name: company.name,
    functionalCurrency: company.functional_currency,
    companyNumber: company.company_number ?? "",
    industry: company.industry ?? "",
    companyType: company.company_type,
  };
}

export function defaultCompanyCurrency(
  jurisdiction: string | null | undefined,
): string {
  return jurisdiction === "IE" ? "EUR" : "GBP";
}

/** Whether a currency edit may be sent once trial balances exist. */
export function currencyChangeAllowed(input: {
  currentCurrency: string;
  nextCurrency: string;
  hasTrialBalances: boolean;
  acknowledged: boolean;
}): boolean {
  const changing =
    input.nextCurrency.toUpperCase() !== input.currentCurrency.toUpperCase();
  if (!changing || !input.hasTrialBalances) {
    return true;
  }
  return input.acknowledged;
}
