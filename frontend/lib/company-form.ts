/** Silent defaults applied by the DB when creating a company (not shown on create form). */
export const DEFAULT_MATERIALITY_PCT = "10.00";
export const DEFAULT_MATERIALITY_ABS = "1000.00";

export type CompanyEntityFormValues = {
  name: string;
  functionalCurrency: string;
  companyNumber: string;
  industry: string;
  companyType: "trading" | "holding";
};
