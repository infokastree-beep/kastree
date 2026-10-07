/**
 * Adopted-draft PDF download.
 *
 * The browser calls `/backend-api/...` (see getApiBaseUrl) with the Clerk
 * bearer token. A navigation link cannot attach that token.
 */

import { getApiBaseUrl } from "@/lib/api";
import { messageFromPdfBody } from "@/lib/workspace-load-error";

export { messageFromPdfBody, pdfBlockReason } from "@/lib/workspace-load-error";
export type { PdfCheck } from "@/lib/workspace-load-error";

export const DRAFT_PDF_FILENAME = "statutory-statements-draft.pdf";

const PDF_FAILED = "The draft PDF could not be downloaded.";

export async function downloadDraftPdf(
  path: string,
  getToken: () => Promise<string | null>,
): Promise<void> {
  const token = await getToken();
  if (!token) {
    throw new Error("Sign in to download the draft PDF.");
  }
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new Error("Could not reach the server. Check your connection and try again.");
  }
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new Error(messageFromPdfBody(body) ?? PDF_FAILED);
  }
  const type = response.headers.get("content-type") ?? "";
  if (!type.includes("application/pdf")) {
    throw new Error(PDF_FAILED);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = DRAFT_PDF_FILENAME;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
