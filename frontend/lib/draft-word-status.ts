/**
 * Labels for the Outputs Word row. Kept free of path aliases so the node test can import it.
 */

export const WORD_DOWNLOAD_LABEL = "Download Word (.docx)";
export const WORD_PROGRESS_LABEL = "Preparing Word…";
export const DRAFT_WORD_FILENAME = "statutory-statements-draft.docx";

export function wordProgressLabel(
  status: "pending" | "running" | "ready" | "failed" | "idle",
): string | null {
  if (status === "pending" || status === "running") {
    return WORD_PROGRESS_LABEL;
  }
  return null;
}
