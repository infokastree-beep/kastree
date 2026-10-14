/** Currency display helpers — Cursor Rules §10.7.

The grouping and the half-even cent match `format_currency` in
`backend/app/services/exporter.py`. Amount strings stay strings. This
function does not add the figures together.
*/

const SYMBOLS: Record<string, string> = {
  GBP: "£",
  USD: "$",
  EUR: "€",
};

const STORED_AMOUNT = /^(-?)(\d+)(?:\.(\d+))?$/;

function currencySymbol(code: string): string {
  const upper = code.trim().toUpperCase();
  if (upper === "") {
    return "";
  }
  return SYMBOLS[upper] ?? upper;
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

function addOne(whole: string): string {
  const digits = whole.replace(/^0+(?=\d)/, "") || "0";
  const out: string[] = [];
  let carry = 1;
  for (let i = digits.length - 1; i >= 0; i -= 1) {
    const sum = Number.parseInt(digits[i] ?? "0", 10) + carry;
    out.push(String(sum % 10));
    carry = sum >= 10 ? 1 : 0;
  }
  if (carry === 1) {
    out.push("1");
  }
  return out.reverse().join("");
}

/** Round half to even on the second decimal place, matching Decimal.quantize. */
function quantizeCents(whole: string, frac: string): { whole: string; cents: string } {
  const kept = (frac + "00").slice(0, 2);
  const rest = frac.length > 2 ? frac.slice(2) : "";
  let cents = Number.parseInt(kept, 10);
  if (roundUp(kept, rest)) {
    cents += 1;
    if (cents === 100) {
      return { whole: addOne(whole), cents: "00" };
    }
  }
  return { whole, cents: String(cents).padStart(2, "0") };
}

function roundUp(kept: string, rest: string): boolean {
  if (rest === "") {
    return false;
  }
  const first = rest[0] ?? "0";
  if (first < "5") {
    return false;
  }
  if (first > "5") {
    return true;
  }
  for (let i = 1; i < rest.length; i += 1) {
    if (rest[i] !== "0") {
      return true;
    }
  }
  const lastKept = Number.parseInt(kept[1] ?? "0", 10);
  return lastKept % 2 === 1;
}

function storedText(amount: string | number): string | null {
  if (typeof amount === "number") {
    if (!Number.isFinite(amount)) {
      return null;
    }
    return amount.toFixed(2);
  }
  const cleaned = amount.trim().replace(/,/g, "").replace(/^\+/, "");
  return STORED_AMOUNT.test(cleaned) ? cleaned : null;
}

/**
 * Format a monetary amount with comma thousands separators for all currencies
 * (GBP/USD/EUR — §10.7; deliberate override of European space grouping for product
 * consistency). Always two decimal places; minus sign for negatives (caller applies
 * red styling).
 */
export function formatCurrency(amount: string | number, currencyCode: string): string {
  const text = storedText(amount);
  if (text == null) {
    return String(amount);
  }
  const match = STORED_AMOUNT.exec(text);
  if (match == null) {
    return String(amount);
  }
  const negative = match[1] === "-";
  const quantized = quantizeCents(match[2] ?? "0", match[3] ?? "");
  const numberPart = `${groupThousands(quantized.whole)}.${quantized.cents}`;
  const zero = numberPart === "0.00";
  const sign = negative && !zero ? "-" : "";
  return `${sign}${currencySymbol(currencyCode)}${numberPart}`;
}

/** A missing engine figure is an em dash. A present figure uses formatCurrency. */
export function formatStoredAmount(
  amount: string | null | undefined,
  currencyCode: string | null | undefined,
): string {
  if (amount == null || amount.trim() === "") {
    return "—";
  }
  return formatCurrency(amount, currencyCode ?? "");
}

export function formatCurrencyCode(currencyCode: string): string {
  return currencyCode.toUpperCase();
}
