/**
 * Detects the adopted-trial-balance sub-line refusal.
 * The sentence is shown unchanged. The account name is the text after "on".
 */

const SUBLINE_GAP =
  /^Product 1 line '([^']*)' on '(.*)' needs a statutory sub-line$/;

export function sublineGapAccount(message: string): string | null {
  const match = SUBLINE_GAP.exec(message.trim());
  if (!match) {
    return null;
  }
  const account = match[2] ?? "";
  return account.length > 0 ? account : null;
}
