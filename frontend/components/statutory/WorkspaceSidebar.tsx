"use client";

import type { WorkspaceSection } from "@/lib/workspace-sections";

type SectionGroup = {
  id: string;
  label: string;
  sections: WorkspaceSection[];
};

function groupsFrom(sections: readonly WorkspaceSection[]): SectionGroup[] {
  const ordered = [...sections].sort((left, right) => left.order - right.order);
  const groups: SectionGroup[] = [];
  for (const section of ordered) {
    const current = groups[groups.length - 1];
    if (current !== undefined && current.id === section.group) {
      current.sections.push(section);
      continue;
    }
    groups.push({
      id: section.group,
      label: section.group_label,
      sections: [section],
    });
  }
  return groups;
}

export function WorkspaceSidebar({
  sections,
  activeId,
  onSelect,
}: {
  sections: readonly WorkspaceSection[];
  activeId: string;
  onSelect: (sectionId: string) => void;
}) {
  return (
    <nav
      aria-label="Draft sections"
      data-testid="statutory-sidebar"
      className="w-56 shrink-0"
    >
      {groupsFrom(sections).map((group) => (
        <div key={group.id} data-testid={`statutory-group-${group.id}`}>
          <p className="px-3 pb-1 pt-3 text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            {group.label}
          </p>
          <ul className="space-y-1">
            {group.sections.map((section) => {
              const active = section.id === activeId;
              return (
                <li key={section.id}>
                  <button
                    type="button"
                    data-testid={`statutory-section-${section.id}`}
                    aria-current={active ? "page" : undefined}
                    onClick={() => onSelect(section.id)}
                    className={`w-full rounded-md px-3 py-2 text-left text-sm ${
                      active
                        ? "bg-accent font-semibold text-accent-foreground"
                        : "text-ink hover:bg-surface-elevated"
                    }`}
                  >
                    {section.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
