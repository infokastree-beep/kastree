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
 * Group an integer digit string with comma thousands separators (§10.7).
 * Locale-independent (does not rely on Intl grouping, which can vary by ICU data).
 * Deliberate: GBP, USD, and EUR all use commas for consistency across the product.
 */
function groupThousands(wholeDigits: string): string {
  const digits = wholeDigits.replace(/^0+(?=\d)/, "") || "0";
  const parts: string[] = [];
  for (let i = digits.length; i > 0; i -= 3) {
    parts.unshift(digits.slice(Math.max(0, i - 3), i));
  }
  return parts.join(",");
}

/**
 * Format a monetary amount with comma thousands separators for all currencies
 * (GBP/USD/EUR — §10.7; deliberate override of European space grouping for product
 * consistency). Always two decimal places; minus sign for negatives (caller applies
 * red styling).
 */
export function formatCurrency(amount: string | number, currencyCode: string): string {
  const value = typeof amount === "string" ? Number.parseFloat(amount) : amount;
  if (!Number.isFinite(value)) {
    return String(amount);
  }

  const upper = currencyCode.toUpperCase();
  const abs = Math.abs(value);
  const fixed = abs.toFixed(2);
  const [whole, frac] = fixed.split(".");
  const numberPart = `${groupThousands(whole ?? "0")}.${frac ?? "00"}`;

  const sign = value < 0 ? "-" : "";
  return `${sign}${currencySymbol(upper)}${numberPart}`;
}

export function formatCurrencyCode(currencyCode: string): string {
  return currencyCode.toUpperCase();
}
