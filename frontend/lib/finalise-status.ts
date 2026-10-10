/** Review-dashboard sentence. A draft that passed its checks can finalise. */

const CURRENCY_NOTICE =
  /^Company currency is ([A-Z]{3})\. Confirm this is intended\.$/;

export function currencyCodeFromNotice(message: string): string | null {
  return CURRENCY_NOTICE.exec(message)?.[1] ?? null;
}

export function finaliseStatusLine(input: {
  canFinalise: boolean;
  tbVersionId: string | null;
}): string {
  if (!input.canFinalise) {
    return " Not ready to finalise.";
  }
  return " Ready to finalise.";
}
