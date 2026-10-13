/** Chooses which preview anchor a note link should scroll to. */

export type PreviewChild = {
  id: string;
  number: number | null;
  label: string;
  anchor: string;
  note_class?: string | null;
  note_class_label?: string | null;
  status?: "complete" | "missing";
};

/** Pack class order. A test checks this list against the pack file. */
export const NOTE_CLASS_ORDER = [
  "policies",
  "fixed assets",
  "current assets",
  "creditors",
  "equity",
  "other",
] as const;

export type NoteClassGroup<T> = {
  id: string;
  label: string;
  items: T[];
};

export function groupByNoteClass<
  T extends { note_class?: string | null; note_class_label?: string | null },
>(items: readonly T[], classOrder: readonly string[]): NoteClassGroup<T>[] {
  const buckets = new Map<string, NoteClassGroup<T>>();
  for (const item of items) {
    const raw = item.note_class?.trim() ?? "";
    const id = raw === "" ? "other" : raw;
    const label = item.note_class_label?.trim() || "Other";
    const existing = buckets.get(id);
    if (existing) {
      existing.items.push(item);
      continue;
    }
    buckets.set(id, { id, label, items: [item] });
  }
  const ordered: NoteClassGroup<T>[] = [];
  for (const id of classOrder) {
    const group = buckets.get(id);
    if (group) {
      ordered.push(group);
      buckets.delete(id);
    }
  }
  for (const group of Array.from(buckets.values())) {
    ordered.push(group);
  }
  return ordered;
}

const GENERAL_NOTE_LABELS = ["Company information", "Accounting policies"] as const;

/** Sidebar only. General is first. Each note keeps the number the PDF printed. */
export function sidebarNoteGroups<
  T extends {
    label: string;
    number?: number | null;
    note_class?: string | null;
    note_class_label?: string | null;
  },
>(items: readonly T[], classOrder: readonly string[]): NoteClassGroup<T>[] {
  const general: T[] = [];
  const rest: T[] = [];
  for (const item of items) {
    if (
      item.label === "Company information" ||
      item.label === "Accounting policies"
    ) {
      general.push(item);
    } else {
      rest.push(item);
    }
  }
  general.sort(
    (left, right) =>
      GENERAL_NOTE_LABELS.indexOf(
        left.label as (typeof GENERAL_NOTE_LABELS)[number],
      ) -
      GENERAL_NOTE_LABELS.indexOf(
        right.label as (typeof GENERAL_NOTE_LABELS)[number],
      ),
  );
  const groups = groupByNoteClass(rest, classOrder);
  if (general.length === 0) {
    return groups;
  }
  return [{ id: "general", label: "General", items: general }, ...groups];
}

export type SectionOutline = {
  sections: { id: string; children: PreviewChild[] }[];
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
