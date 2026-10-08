/** Chooses which preview anchor a note link should scroll to. */

export type PreviewChild = {
  id: string;
  number: number | null;
  label: string;
  anchor: string;
};

export type StatutoryPreview = {
  section_id: string;
  anchor: string;
  row_version: number;
  preview_revision: string;
  watermark: string;
  html: string;
  section_html_sha256: string;
  children: PreviewChild[];
};

const ANCHOR = /^[A-Za-z0-9_-]+$/;

export function scrollAnchorFor(
  requested: string | null,
  children: readonly PreviewChild[],
): string | null {
  if (requested == null || requested === "") {
    return null;
  }
  const match = children.find(
    (child) => child.id === requested || child.anchor === requested,
  );
  if (!match || !ANCHOR.test(match.anchor)) {
    return null;
  }
  return match.anchor;
}

export function showsPageNumberNote(sectionId: string): boolean {
  return sectionId === "contents";
}
