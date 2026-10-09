"use client";

import { useEffect, useState } from "react";
import type { PreviewChild } from "@/lib/section-preview";
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
  childrenBySection = {},
  activeChildId = null,
  onSelect,
  onSelectChild,
}: {
  sections: readonly WorkspaceSection[];
  activeId: string;
  childrenBySection?: Readonly<Record<string, readonly PreviewChild[]>>;
  activeChildId?: string | null;
  onSelect: (sectionId: string) => void;
  onSelectChild?: (sectionId: string, childId: string) => void;
}) {
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const [collapsedChildren, setCollapsedChildren] = useState<
    Record<string, boolean>
  >({});

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
                  const off = section.enabled === false;
                  const children = childrenBySection[section.id] ?? [];
                  const childrenOpen = collapsedChildren[section.id] !== true;
                  return (
                    <li key={section.id} className={off ? "opacity-60" : undefined}>
                      <div className="flex items-start gap-1">
                        {children.length > 0 ? (
                          <button
                            type="button"
                            aria-expanded={childrenOpen}
                            data-testid={`statutory-children-toggle-${section.id}`}
                            onClick={() =>
                              setCollapsedChildren((current) => ({
                                ...current,
                                [section.id]: childrenOpen,
                              }))
                            }
                            className="mt-2 w-4 shrink-0 text-xs text-soft"
                          >
                            <span aria-hidden="true">{childrenOpen ? "▾" : "▸"}</span>
                          </button>
                        ) : (
                          <span className="w-4 shrink-0" />
                        )}
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
                          {section.lock === "locked" ? (
                            <span className="ml-2 text-[10px] font-semibold uppercase tracking-[0.08em] opacity-70">lock</span>
                          ) : null}
                          {off ? (
                            <span className="ml-2 text-[10px] font-semibold uppercase tracking-[0.08em] opacity-70">off</span>
                          ) : null}
                          {section.built === false ? (
                            <span className="mt-0.5 block text-[10px] font-semibold uppercase tracking-[0.08em] opacity-70">
                              not built
                            </span>
                          ) : null}
                        </button>
                      </div>
                      {childrenOpen && children.length > 0 ? (
                        <ul className="mb-1 space-y-0.5 pl-7">
                          {children.map((child) => {
                            const current =
                              active && child.id === activeChildId;
                            return (
                              <li key={child.id}>
                                <button
                                  type="button"
                                  data-testid={`statutory-child-${child.anchor}`}
                                  aria-current={current ? "true" : undefined}
                                  onClick={() =>
                                    onSelectChild?.(section.id, child.id)
                                  }
                                  className={`w-full rounded-md px-3 py-1.5 text-left text-xs ${
                                    current
                                      ? "bg-accent font-semibold text-accent-foreground"
                                      : "text-ink-secondary hover:bg-surface-elevated"
                                  }`}
                                >
                                  {child.number != null
                                    ? `${child.number}. ${child.label}`
                                    : child.label}
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      ) : null}
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
