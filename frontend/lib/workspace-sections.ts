/** Picks a sidebar from a framework catalogue. It does not know FRS 102. */

export type WorkspaceSection = {
  id: string;
  label: string;
};

export type ReportingFramework = {
  id: string;
  label: string;
  available: boolean;
  sections: WorkspaceSection[];
};

const FALLBACK: WorkspaceSection[] = [
  { id: "report-setup", label: "Report setup" },
  { id: "review", label: "Review dashboard" },
];

export function sectionsForFramework(
  frameworks: readonly ReportingFramework[],
  frameworkId: string,
): WorkspaceSection[] {
  const match = frameworks.find((framework) => framework.id === frameworkId);
  if (!match) {
    return FALLBACK;
  }
  return match.sections;
}

export function activeSection(
  sections: readonly WorkspaceSection[],
  requested: string | null,
): string {
  if (requested && sections.some((section) => section.id === requested)) {
    return requested;
  }
  if (sections.some((section) => section.id === "review")) {
    return "review";
  }
  return sections[0]?.id ?? "report-setup";
}
