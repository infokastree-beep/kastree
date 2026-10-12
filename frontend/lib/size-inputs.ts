/** Display and request text for stored size-test inputs. */

export type SizeInputFields = {
  size_current_turnover: string | null;
  size_current_balance_sheet: string | null;
  size_current_employees: number | null;
  size_preceding_turnover: string | null;
  size_preceding_balance_sheet: string | null;
  size_preceding_employees: number | null;
};

export type SizeYearRequest = {
  turnover: string;
  balance_sheet_total: string;
  employees: number;
};

const NOT_RECORDED = "not recorded";

/** Exact cent text for the size-eligibility request. Commas are typing only. */
export function sizeAmountToApi(raw: string): string | null {
  const cleaned = raw.replace(/[£€$,\s]/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) {
    return null;
  }
  const [whole, frac = ""] = cleaned.split(".");
  return `${whole}.${frac.padEnd(2, "0")}`;
}

export function sizeEmployeesToApi(raw: string): number | null {
  if (!/^\d+$/.test(raw.trim())) {
    return null;
  }
  return Number(raw.trim());
}

export function sizeMoneyLabel(
  value: string | null,
  currency: string | null,
  format: (amount: string, currency: string) => string,
): string {
  if (value == null || value.trim() === "") {
    return NOT_RECORDED;
  }
  if (currency == null || currency.trim() === "") {
    return value;
  }
  return format(value, currency);
}

export function sizeEmployeesLabel(value: number | null): string {
  if (value == null) {
    return NOT_RECORDED;
  }
  return String(value);
}
