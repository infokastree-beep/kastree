"use client";

import { useEffect, useState } from "react";
import {
  groupIsOpen,
  readClosedGroups,
  writeClosedGroups,
  type WorkspaceSection,
} from "@/lib/workspace-sections";

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
  const [closed, setClosed] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setClosed(readClosedGroups());
  }, []);

  function toggleGroup(groupId: string): void {
    setClosed((current) => {
      const next = { ...current };
      if (groupIsOpen(current, groupId)) {
        next[groupId] = false;
      } else {
        delete next[groupId];
      }
      writeClosedGroups(next);
      return next;
    });
  }

  return (
    <nav
      aria-label="Draft sections"
      data-testid="statutory-sidebar"
      className="w-56 shrink-0"
    >
      {groupsFrom(sections).map((group) => {
        const open = groupIsOpen(closed, group.id);
        return (
          <div key={group.id} data-testid={`statutory-group-${group.id}`}>
            <button
              type="button"
              aria-expanded={open}
              data-testid={`statutory-group-toggle-${group.id}`}
              onClick={() => toggleGroup(group.id)}
              className="flex w-full items-center justify-between px-3 pb-1 pt-3 text-left text-xs font-semibold uppercase tracking-[0.12em] text-soft"
            >
              <span>{group.label}</span>
              <span aria-hidden="true">{open ? "▾" : "▸"}</span>
            </button>
            {open ? (
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
                        {section.built === false ? (
                          <span className="mt-0.5 block text-[10px] font-semibold uppercase tracking-[0.08em] opacity-70">
                            not built
                          </span>
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}
