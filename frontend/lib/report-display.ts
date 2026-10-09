/** Display-only rounding. The stored amount string is not rewritten. */

export type RoundingMode = "unit" | "thousands";
export type StatementType = "draft" | "compilation";

const SCALE = 6;

function tenTo(exp: number): bigint {
  let value = BigInt(1);
  for (let index = 0; index < exp; index += 1) {
    value *= BigInt(10);
  }
  return value;
}

function roundHalfAwayFromZero(numerator: bigint, denominator: bigint): bigint {
  const negative = numerator < BigInt(0);
  const magnitude = negative ? -numerator : numerator;
  const quotient = magnitude / denominator;
  const remainder = magnitude % denominator;
  const rounded =
    remainder * BigInt(2) >= denominator ? quotient + BigInt(1) : quotient;
  return negative ? -rounded : rounded;
}

/** Display rounding. Unparseable text is returned unchanged. */
export function displayAmount(stored: string, rounding: RoundingMode): string {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(stored.trim());
  if (!match) {
    return stored;
  }
  const fraction = (match[3] ?? "").slice(0, SCALE).padEnd(SCALE, "0");
  const scaled = BigInt(`${match[2]}${fraction}`);
  const signed = match[1] === "-" ? -scaled : scaled;
  const unit = tenTo(SCALE);
  const divisor = rounding === "thousands" ? unit * BigInt(1000) : unit;
  return roundHalfAwayFromZero(signed, divisor).toString();
}
