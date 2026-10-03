"use client";

import type { WorkspaceSection } from "@/lib/workspace-sections";

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
      <ul className="space-y-1">
        {sections.map((section) => {
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
    </nav>
  );
}
