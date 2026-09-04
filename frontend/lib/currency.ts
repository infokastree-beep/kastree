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
 * Group an integer digit string with the §10.7 thousands separator:
 * comma for GBP/USD, space for EUR. Locale-independent (does not rely on Intl
 * grouping, which can vary by ICU data).
 */
function groupThousands(wholeDigits: string, separator: "," | " "): string {
  const digits = wholeDigits.replace(/^0+(?=\d)/, "") || "0";
  const parts: string[] = [];
  for (let i = digits.length; i > 0; i -= 3) {
    parts.unshift(digits.slice(Math.max(0, i - 3), i));
  }
  return parts.join(separator);
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
  const separator: "," | " " = upper === "EUR" ? " " : ",";
  const abs = Math.abs(value);
  const fixed = abs.toFixed(2);
  const [whole, frac] = fixed.split(".");
  const numberPart = `${groupThousands(whole ?? "0", separator)}.${frac ?? "00"}`;

  const sign = value < 0 ? "-" : "";
  return `${sign}${currencySymbol(upper)}${numberPart}`;
}

export function formatCurrencyCode(currencyCode: string): string {
  return currencyCode.toUpperCase();
}
