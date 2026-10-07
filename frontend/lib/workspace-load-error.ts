/**
 * Detects the adopted-trial-balance sub-line refusal.
 * The sentence is shown unchanged. The account name is the text after "on".
 */

const SUBLINE_GAP =
  /^Product 1 line '([^']*)' on '(.*)' needs a statutory sub-line$/;

export type PdfCheck = {
  code: string;
  passed: boolean;
  message: string;
};

export function sublineGapAccount(message: string): string | null {
  const match = SUBLINE_GAP.exec(message.trim());
  if (!match) {
    return null;
  }
  const account = match[2] ?? "";
  return account.length > 0 ? account : null;
}

export function messageFromPdfBody(body: unknown): string | null {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return null;
  }
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") {
    const text = detail.trim();
    if (text.length === 0 || /^API \d+$/.test(text)) {
      return null;
    }
    return text;
  }
  if (Array.isArray(detail)) {
    const parts = detail.flatMap((item) => {
      if (typeof item === "object" && item !== null && "msg" in item) {
        const msg = (item as { msg: unknown }).msg;
        return typeof msg === "string" && msg.trim().length > 0 ? [msg.trim()] : [];
      }
      return [];
    });
    return parts.length > 0 ? parts.join(" ") : null;
  }
  if (typeof detail === "object" && detail !== null && "message" in detail) {
    const message = (detail as { message: unknown }).message;
    if (typeof message === "string" && message.trim().length > 0) {
      return message.trim();
    }
  }
  return null;
}

export function pdfBlockReason(input: {
  statementsError: string | null;
  dashboardError: string | null;
  renderable: boolean | null;
  checks: readonly PdfCheck[];
}): string | null {
  const account =
    sublineGapAccount(input.statementsError ?? "") ??
    sublineGapAccount(input.dashboardError ?? "");
  if (account !== null) {
    return `Confirm the sub-line for ${account} first`;
  }
  if (input.checks.some((check) => check.code === "V-GATE-001" && !check.passed)) {
    return "Mark the first financial period first";
  }
  if (input.statementsError) {
    return input.statementsError;
  }
  if (input.renderable === false) {
    const failed = input.checks.find((check) => !check.passed);
    return failed?.message ?? "Statutory statements are not renderable";
  }
  return null;
}
