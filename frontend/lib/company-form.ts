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
