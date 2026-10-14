/** Sidebar rows for facts that belong on a document section. */

import type { DisclosureQuestion } from "@/lib/disclosure-groups";
import type { PreviewChild } from "@/lib/section-preview";
import type { WorkspaceSection } from "@/lib/workspace-sections";

export type ReportInterest = {
  name: string;
  role: "director" | "secretary";
  at_start: {
    interested: boolean;
    holdings: { undertaking: string; shares: number; amount: string }[];
  };
  at_end: {
    interested: boolean;
    holdings: { undertaking: string; shares: number; amount: string }[];
  };
};

/** Facts the directors' report save replaces. Other company fields stay off it. */
export type DirectorsReportStored = {
  accounting_records_location: string | null;
  interim_dividend: string | null;
  recommended_dividend: string | null;
  share_interests: ReportInterest[];
  own_shares_particulars: string | null;
  subsequent_events_particulars: string | null;
  research_development_relevant: boolean | null;
  research_development_detail: string | null;
  political_donations_relevant: boolean | null;
  political_donations_detail: string | null;
  accounting_period_change_filed: boolean | null;
};

export type SectionFacts = DirectorsReportStored & {
  principal_activity: string | null;
  secretary: string | null;
  directors: { name: string }[];
  compilation_date?: string | null;
  compilation_signatory?: string | null;
};

export type InputStatus = "complete" | "missing";

function taken<K extends keyof DirectorsReportStored>(
  stored: DirectorsReportStored,
  patch: Partial<DirectorsReportStored>,
  key: K,
): DirectorsReportStored[K] {
  if (Object.prototype.hasOwnProperty.call(patch, key)) {
    return patch[key] as DirectorsReportStored[K];
  }
  return stored[key];
}

export function directorsReportWrite(
  stored: DirectorsReportStored,
  patch: Partial<DirectorsReportStored>,
): DirectorsReportStored {
  return {
    accounting_records_location: taken(stored, patch, "accounting_records_location"),
    interim_dividend: taken(stored, patch, "interim_dividend"),
    recommended_dividend: taken(stored, patch, "recommended_dividend"),
    share_interests: taken(stored, patch, "share_interests"),
    own_shares_particulars: taken(stored, patch, "own_shares_particulars"),
    subsequent_events_particulars: taken(
      stored,
      patch,
      "subsequent_events_particulars",
    ),
    research_development_relevant: taken(
      stored,
      patch,
      "research_development_relevant",
    ),
    research_development_detail: taken(stored, patch, "research_development_detail"),
    political_donations_relevant: taken(
      stored,
      patch,
      "political_donations_relevant",
    ),
    political_donations_detail: taken(stored, patch, "political_donations_detail"),
    accounting_period_change_filed: taken(
      stored,
      patch,
      "accounting_period_change_filed",
    ),
  };
}

function recorded(value: string | null | undefined): boolean {
  return (value ?? "").trim() !== "";
}

export function recordsComplete(details: DirectorsReportStored | null): boolean {
  if (details == null) {
    return false;
  }
  return (
    recorded(details.accounting_records_location) &&
    recorded(details.interim_dividend) &&
    recorded(details.recommended_dividend)
  );
}

export function interestsComplete(details: SectionFacts | null): boolean {
  if (details == null) {
    return false;
  }
  const needed = new Set<string>();
  for (const director of details.directors) {
    const name = director.name.trim();
    if (name !== "") {
      needed.add(`${name.toLowerCase()}|director`);
    }
  }
  const secretary = (details.secretary ?? "").trim();
  if (secretary !== "") {
    needed.add(`${secretary.toLowerCase()}|secretary`);
  }
  if (needed.size === 0) {
    return false;
  }
  const found = new Set(
    details.share_interests.map(
      (person) => `${person.name.trim().toLowerCase()}|${person.role}`,
    ),
  );
  for (const key of Array.from(needed)) {
    if (!found.has(key)) {
      return false;
    }
  }
  return true;
}

const OTHER_GATES = new Set(["V-CO-033"]);

export function otherMattersComplete(
  details: DirectorsReportStored | null,
  failedCodes: readonly string[],
): boolean {
  if (details == null) {
    return false;
  }
  if (failedCodes.some((code) => OTHER_GATES.has(code))) {
    return false;
  }
  if (details.research_development_relevant == null) {
    return false;
  }
  if (
    details.research_development_relevant &&
    !recorded(details.research_development_detail)
  ) {
    return false;
  }
  if (details.political_donations_relevant == null) {
    return false;
  }
  if (
    details.political_donations_relevant &&
    !recorded(details.political_donations_detail)
  ) {
    return false;
  }
  return details.accounting_period_change_filed != null;
}

function mark(ok: boolean): InputStatus {
  return ok ? "complete" : "missing";
}

export const DIRECTORS_REPORT_ROW_IDS = [
  "accounting-records",
  "share-interests",
  "other-matters",
  "principal-activity",
] as const;

export function directorsReportChildren(
  details: SectionFacts | null,
  failedCodes: readonly string[],
): PreviewChild[] {
  return [
    {
      id: "accounting-records",
      number: null,
      label: "Accounting records and dividends",
      anchor: "accounting-records",
      status: mark(recordsComplete(details)),
    },
    {
      id: "share-interests",
      number: null,
      label: "Interests in shares",
      anchor: "share-interests",
      status: mark(interestsComplete(details)),
    },
    {
      id: "other-matters",
      number: null,
      label: "Other matters",
      anchor: "other-matters",
      status: mark(otherMattersComplete(details, failedCodes)),
    },
    {
      id: "principal-activity",
      number: null,
      label: "Principal activities",
      anchor: "principal-activity",
      status: mark(recorded(details?.principal_activity)),
    },
  ];
}

export function compilationDateChild(details: SectionFacts | null): PreviewChild {
  const complete =
    details != null &&
    recorded(details.compilation_date) &&
    recorded(details.compilation_signatory);
  return {
    id: "compilation-date",
    number: null,
    label: "Date and signatory",
    anchor: "compilation-date",
    status: mark(complete),
  };
}

export type ShareClassInput = {
  class_name: string;
  authorised_number: number | null;
  issued_number: number;
  nominal_value: string;
};

export type ParticularsStored = {
  related_party_particulars: string | null;
  directors_remuneration_particulars: string | null;
  loan_terms_particulars: string | null;
  guarantee_particulars: string | null;
  subsequent_events_particulars: string | null;
  share_classes: ShareClassInput[];
};

function answerYes(
  questions: readonly DisclosureQuestion[],
  flag: string,
): boolean {
  return questions.some(
    (question) => question.flag_name === flag && question.answer === "yes",
  );
}

function yesSlot(
  questions: readonly DisclosureQuestion[],
  flags: readonly string[],
  text: string | null | undefined,
): InputStatus {
  const required = flags.some((flag) => answerYes(questions, flag));
  if (!required) {
    return "complete";
  }
  return mark(recorded(text));
}

export function notesParticularChildren(
  details: Partial<ParticularsStored> | null,
  questions: readonly DisclosureQuestion[],
): PreviewChild[] {
  const classes = details?.share_classes ?? [];
  const shareComplete = classes.some((row) => row.class_name.trim() !== "");
  return [
    {
      id: "share-capital",
      number: null,
      label: "Share capital by class",
      anchor: "share-capital",
      note_class: "equity",
      note_class_label: "Equity",
      status: mark(shareComplete),
    },
    {
      id: "related-parties",
      number: null,
      label: "Related parties",
      anchor: "related-parties",
      note_class: "other",
      note_class_label: "Other",
      status: yesSlot(questions, ["RPT_EXISTS"], details?.related_party_particulars),
    },
    {
      id: "directors-remuneration",
      number: null,
      label: "Directors' remuneration",
      anchor: "directors-remuneration",
      note_class: "other",
      note_class_label: "Other",
      status: yesSlot(
        questions,
        ["DIRECTORS_EXIST"],
        details?.directors_remuneration_particulars,
      ),
    },
    {
      id: "loans-and-credit",
      number: null,
      label: "Loans and credit",
      anchor: "loans-and-credit",
      note_class: "creditors",
      note_class_label: "Creditors",
      status: yesSlot(
        questions,
        ["CONNECTED_LOANS", "DIRECTOR_LOAN_AGREEMENTS"],
        details?.loan_terms_particulars,
      ),
    },
    {
      id: "guarantees",
      number: null,
      label: "Guarantees",
      anchor: "guarantees",
      note_class: "other",
      note_class_label: "Other",
      status: yesSlot(
        questions,
        ["GUARANTEES_EXIST", "DIRECTOR_GUARANTEES", "DIRECTOR_GUARANTEE_AGREEMENTS"],
        details?.guarantee_particulars,
      ),
    },
    {
      id: "subsequent-events",
      number: null,
      label: "Post-balance-sheet events",
      anchor: "subsequent-events",
      note_class: "other",
      note_class_label: "Other",
      status: yesSlot(
        questions,
        ["SUBSEQUENT_EVENTS"],
        details?.subsequent_events_particulars,
      ),
    },
  ];
}

export function sidebarInputChildren(
  outline: Readonly<Record<string, PreviewChild[]>>,
  details: SectionFacts | null,
  failedCodes: readonly string[],
  questions: readonly DisclosureQuestion[] = [],
): Record<string, PreviewChild[]> {
  const next: Record<string, PreviewChild[]> = { ...outline };
  const directors = directorsReportChildren(details, failedCodes);
  const known = new Set<string>(DIRECTORS_REPORT_ROW_IDS);
  const extra = (outline["directors-report"] ?? []).filter(
    (child) => !known.has(child.id),
  );
  next["directors-report"] = [...directors, ...extra];
  const compilation = (outline.compilation ?? []).filter(
    (child) => child.id !== "compilation-date",
  );
  next.compilation = [...compilation, compilationDateChild(details)];
  const notes = notesParticularChildren(details, questions);
  const noteIds = new Set(notes.map((child) => child.id));
  const existing = (outline.notes ?? []).filter((child) => !noteIds.has(child.id));
  next.notes = [...existing, ...notes];
  return next;
}

export const SIGNATORIES_SECTION: WorkspaceSection = {
  id: "signatories",
  label: "Signatories",
  group: "report-options",
  group_label: "Report options",
  order: 3.5,
};

export function withSignatories(
  sections: readonly WorkspaceSection[],
): WorkspaceSection[] {
  if (sections.some((section) => section.id === "signatories")) {
    return [...sections];
  }
  if (!sections.some((section) => section.id === "sections-setup")) {
    return [...sections];
  }
  return [...sections, SIGNATORIES_SECTION];
}

export function directorsReportNote(noteId: string | null): string {
  if (
    noteId === "share-interests" ||
    noteId === "other-matters" ||
    noteId === "principal-activity"
  ) {
    return noteId;
  }
  return "accounting-records";
}

export function directorsReportPart(
  noteId: string | null,
): "records" | "interests" | "other" | "principal-activity" {
  const note = directorsReportNote(noteId);
  if (note === "share-interests") {
    return "interests";
  }
  if (note === "other-matters") {
    return "other";
  }
  if (note === "principal-activity") {
    return "principal-activity";
  }
  return "records";
}

export function showCompilationForm(noteId: string | null): boolean {
  return noteId == null || noteId === "" || noteId === "compilation-date";
}
