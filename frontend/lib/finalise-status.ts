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

export const FINALISED_STATE = "FINAL";

export const CARRIED_ACK_LABEL =
  "I have reviewed the carried-over disclosure answers.";

export const FINALISE_LOCK_NOTE =
  "Finalising locks this draft. Corrections require a new version.";

export const FINALISED_409 = [
  "Directors have not been recorded.",
  "Carried-over disclosure answers have not been acknowledged.",
  "FINAL output is never recomputed",
  "row_version does not match",
  "critical checks block FINAL",
  "evidence graph does not tie",
] as const;

export function canOfferFinalise(
  role: string | undefined,
  status: string | undefined,
): boolean {
  return (role === "owner" || role === "admin") && status !== "final" && status != null;
}

export function carriedAcknowledgementRequired(names: readonly string[]): boolean {
  return names.length > 0;
}

export function pdfDownloadLabel(status: string | undefined): string {
  return status === "final" ? "Download final PDF" : "Download draft PDF";
}

export function finaliseFailureMessage(
  status: number,
  detail: string | null,
): string {
  if (status === 403) {
    return "You don't have permission to access this resource.";
  }
  const text = detail?.trim() ?? "";
  if (status === 409 && text.length > 0) {
    return text;
  }
  return "This draft could not be finalised.";
}
