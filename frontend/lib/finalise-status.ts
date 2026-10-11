/** Review-dashboard sentence. A draft that passed its checks can finalise. */

export const WORDING_BANNER =
  "Statutory wording not yet reviewed by a qualified reviewer";

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

/** True only when the server says the wording is signed off. A missing flag stays unsigned. */
export function wordingSignedOffFromServer(
  access: { wording_signed_off?: boolean } | undefined,
): boolean {
  return access?.wording_signed_off === true;
}

export function finalStateLabel(wordingSignedOff: boolean): string {
  if (wordingSignedOff) {
    return FINALISED_STATE;
  }
  return `${FINALISED_STATE} — ${WORDING_BANNER}`;
}

export function shownStatus(status: string, wordingSignedOff: boolean): string {
  if (status !== "final" || wordingSignedOff) {
    return status;
  }
  return `final — ${WORDING_BANNER}`;
}

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

export function pdfDownloadLabel(
  status: string | undefined,
  wordingSignedOff = false,
): string {
  if (status !== "final") {
    return "Download draft PDF";
  }
  if (wordingSignedOff) {
    return "Download final PDF";
  }
  return `Download final PDF — ${WORDING_BANNER}`;
}

export function wordDownloadLabel(
  status: string | undefined,
  wordingSignedOff = false,
): string {
  if (status !== "final" || wordingSignedOff) {
    return "Download Word (.docx)";
  }
  return `Download Word (.docx) — ${WORDING_BANNER}`;
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
