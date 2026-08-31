/** Currency display helpers — Cursor Rules §10.7. */

function currencySymbol(code: string): string {
  const upper = code.toUpperCase();
  const parts = new Intl.NumberFormat("en", {
    style: "currency",
    currency: upper,
    currencyDisplay: "narrowSymbol",
  }).formatToParts(0);
  return parts.find((part) => part.type === "currency")?.value ?? upper;
}

/**
 * Format a monetary amount with the correct thousands separator for the currency:
 * comma for GBP/USD, space for EUR (§10.7). Always two decimal places; minus sign
 * for negatives (caller applies red styling).
 */
export function formatCurrency(amount: string | number, currencyCode: string): string {
  const value = typeof amount === "string" ? Number.parseFloat(amount) : amount;
  if (!Number.isFinite(value)) {
    return String(amount);
  }

  const upper = currencyCode.toUpperCase();
  const absFormatted = new Intl.NumberFormat("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(value));

  const numberPart =
    upper === "EUR" ? absFormatted.replace(/,/g, " ") : absFormatted;

  const sign = value < 0 ? "-" : "";
  return `${sign}${currencySymbol(upper)}${numberPart}`;
}

export function formatCurrencyCode(currencyCode: string): string {
  return currencyCode.toUpperCase();
}
