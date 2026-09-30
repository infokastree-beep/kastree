import type { ExportFormat } from "@/types";

export type ExportAnchorAttributes = {
  href: string;
  rel: "noopener noreferrer";
  /** Set only for PDF so the browser renders the pack in a new tab. */
  target?: "_blank";
};

/**
 * Link attributes for a completed export.
 *
 * PDF opens in a new tab (`target="_blank"`) and is stored as
 * `Content-Disposition: inline`, so the Kastree page stays put and the PDF
 * renders. Excel and CSV do not set `download`: browsers ignore that attribute
 * on cross-origin presigned URLs. Those objects are stored as
 * `Content-Disposition: attachment`, which is what starts the file save.
 */
export function exportAnchorAttributes(
  fileUrl: string,
  format: ExportFormat,
): ExportAnchorAttributes {
  const base: ExportAnchorAttributes = {
    href: fileUrl,
    rel: "noopener noreferrer",
  };
  if (format === "pdf") {
    return { ...base, target: "_blank" };
  }
  return base;
}
