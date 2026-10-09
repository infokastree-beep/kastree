"use client";

import { useState } from "react";
import type { WorkspaceSection } from "@/lib/workspace-sections";

export function SectionsSetup({
  title,
  sections,
  onToggle,
  togglesEnabled,
  canReset,
  onReset,
}: {
  title: string;
  sections: readonly WorkspaceSection[];
  onToggle: (sectionId: string, enabled: boolean) => void;
  togglesEnabled: boolean;
  canReset: boolean;
  onReset: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const rows = sections.filter(
    (section) => section.group === "sections" && section.id !== "sections-setup",
  );
  return (
    <section className="space-y-3" data-testid="statutory-sections-setup">
      <h2 className="text-sm font-semibold text-ink">{title}</h2>
      <ul className="divide-y divide-line rounded-md border border-line">
        {rows.map((section) => (
          <li
            key={section.id}
            className="flex items-center justify-between gap-3 px-3 py-2"
          >
            <span className="text-sm text-ink">
              {section.label}
              {section.built === false ? (
                <span className="mt-0.5 block text-[10px] font-semibold uppercase tracking-[0.08em] opacity-70">
                  not built
                </span>
              ) : null}
            </span>
            {section.lock === "user" ? (
              <input
                type="checkbox"
                className="h-4 w-4 shrink-0"
                checked={section.enabled === true}
                disabled={togglesEnabled !== true}
                aria-label={`Include ${section.label}`}
                data-testid={`statutory-toggle-${section.id}`}
                onChange={(event) => onToggle(section.id, event.target.checked)}
              />
            ) : (
              <span className="flex items-center gap-2 text-xs text-soft">
                <input
                  type="checkbox"
                  className="h-4 w-4 shrink-0"
                  checked
                  disabled
                  aria-label={`Include ${section.label}`}
                  data-testid={`statutory-toggle-${section.id}`}
                />
                locked
              </span>
            )}
          </li>
        ))}
      </ul>
      {canReset ? (
        confirming ? (
          <div className="flex gap-2">
            <button
              type="button"
              data-testid="statutory-reset-sections-confirm"
              className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground"
              onClick={() => {
                setConfirming(false);
                onReset();
              }}
            >
              Confirm reset
            </button>
            <button
              type="button"
              className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink"
              onClick={() => setConfirming(false)}
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            data-testid="statutory-reset-sections"
            className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink"
            onClick={() => setConfirming(true)}
          >
            Reset to pack defaults
          </button>
        )
      ) : null}
    </section>
  );
}
