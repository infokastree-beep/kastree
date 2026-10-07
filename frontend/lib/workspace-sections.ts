/** Picks a sidebar from a framework catalogue. It does not know a framework. */

export type WorkspaceSection = {
  id: string;
  label: string;
  group: string;
  group_label: string;
  order: number;
};

export type ReportingFramework = {
  id: string;
  label: string;
  available: boolean;
  sections: WorkspaceSection[];
};

const FALLBACK: WorkspaceSection[] = [
  {
    id: "review",
    label: "Review dashboard",
    group: "overview",
    group_label: "Overview",
    order: 1,
  },
  {
    id: "report-setup",
    label: "Report setup",
    group: "report-options",
    group_label: "Report options",
    order: 2,
  },
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
