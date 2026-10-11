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

const GENERIC_SERVER = new Set(["Internal Server Error", "Something went wrong."]);

export function requestIdFromBody(body: unknown): string | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const top = (body as { request_id?: unknown }).request_id;
  if (typeof top === "string" && top.trim().length > 0) {
    return top.trim();
  }
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "object" && detail !== null && "request_id" in detail) {
    const nested = (detail as { request_id?: unknown }).request_id;
    if (typeof nested === "string" && nested.trim().length > 0) {
      return nested.trim();
    }
  }
  return null;
}

export type FinaliseFailurePart =
  | { kind: "text"; text: string }
  | { kind: "link"; text: string; href: string };

const FAILURE_LINK =
  /\[([^\]]+)\]\((\/year-ends\/[0-9a-fA-F-]{36}\/draft\?section=[a-z0-9-]+)\)/g;

/** Split a finalise refusal into text and draft-page links. Other URLs stay text. */
export function finaliseFailureParts(message: string): FinaliseFailurePart[] {
  const parts: FinaliseFailurePart[] = [];
  const pattern = new RegExp(FAILURE_LINK.source, "g");
  let last = 0;
  let match = pattern.exec(message);
  while (match !== null) {
    const index = match.index;
    if (index > last) {
      parts.push({ kind: "text", text: message.slice(last, index) });
    }
    parts.push({ kind: "link", text: match[1] ?? "", href: match[2] ?? "" });
    last = index + match[0].length;
    match = pattern.exec(message);
  }
  if (last < message.length) {
    parts.push({ kind: "text", text: message.slice(last) });
  }
  if (parts.length === 0) {
    parts.push({ kind: "text", text: message });
  }
  return parts;
}

export function finaliseFailureMessage(
  status: number,
  detail: string | null,
  requestId: string | null = null,
): string {
  if (status === 403) {
    return "You don't have permission to access this resource.";
  }
  const text = detail?.trim() ?? "";
  const useful =
    text.length > 0 && !GENERIC_SERVER.has(text) && !/^API \d+$/.test(text);
  const reference = requestId?.trim() ?? "";
  if (status >= 500) {
    if (useful && reference.length > 0) {
      return `${text} Quote reference ${reference}.`;
    }
    if (useful) {
      return text;
    }
    if (reference.length > 0) {
      return `Something went wrong while finalising this draft. Quote reference ${reference}.`;
    }
    return "Something went wrong while finalising this draft.";
  }
  if (useful) {
    return text;
  }
  return "This draft could not be finalised.";
}
