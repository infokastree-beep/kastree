/** Picks a sidebar from a framework catalogue. It does not know a framework. */

export type WorkspaceSection = {
  id: string;
  label: string;
  group: string;
  group_label: string;
  order: number;
  lock?: "locked" | "user" | null;
  default?: "on" | "off" | "engine" | null;
  built?: boolean | null;
  enabled?: boolean;
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

export function sectionIsOn(
  section: WorkspaceSection,
  saved: Readonly<Record<string, boolean>> | null | undefined,
): boolean {
  if (section.lock === "locked") {
    return true;
  }
  if (saved != null && Object.prototype.hasOwnProperty.call(saved, section.id)) {
    return saved[section.id] === true;
  }
  return section.default === "on";
}

/** Pack rows the practice has turned off stay on the setup page, not the nav. */
export function navigatorSections(
  sections: readonly WorkspaceSection[],
): WorkspaceSection[] {
  return sections.filter(
    (section) =>
      section.group !== "sections" ||
      section.id === "sections-setup" ||
      section.enabled !== false,
  );
}

export function activeSection(
  sections: readonly WorkspaceSection[],
  requested: string | null,
): string {
  const requestedSection = requested
    ? sections.find((section) => section.id === requested)
    : undefined;
  if (
    requestedSection &&
    requestedSection.group === "sections" &&
    requestedSection.id !== "sections-setup" &&
    requestedSection.enabled === false &&
    sections.some((section) => section.id === "sections-setup")
  ) {
    return "sections-setup";
  }
  if (requestedSection) {
    return requestedSection.id;
  }
  if (sections.some((section) => section.id === "review")) {
    return "review";
  }
  return sections[0]?.id ?? "report-setup";
}

/** Closed groups only. A missing key means the group is open. */
export const SIDEBAR_GROUPS_KEY = "kastree.sidebar.groups.v1";

export function parseGroupState(raw: string | null): Record<string, boolean> {
  if (raw == null || raw === "") {
    return {};
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed == null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    const closed: Record<string, boolean> = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (value === false) {
        closed[key] = false;
      }
    }
    return closed;
  } catch {
    return {};
  }
}

export function groupIsOpen(
  closed: Readonly<Record<string, boolean>>,
  groupId: string,
): boolean {
  return closed[groupId] !== false;
}

export function readClosedGroups(): Record<string, boolean> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    return parseGroupState(window.localStorage.getItem(SIDEBAR_GROUPS_KEY));
  } catch {
    return {};
  }
}

export function writeClosedGroups(closed: Readonly<Record<string, boolean>>): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(SIDEBAR_GROUPS_KEY, JSON.stringify(closed));
  } catch {
    // A private-mode browser still collapses the group for this visit.
  }
}
