/** Review-dashboard sentence. Adopted drafts cannot finalise yet. */

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
  if (input.tbVersionId == null) {
    return " Checks passed. Finalising is not yet available for this draft.";
  }
  return " Ready to finalise.";
}
