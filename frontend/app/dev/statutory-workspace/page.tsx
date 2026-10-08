"use client";

/**
 * Auth-free preview of the statutory sidebar and display-only report setup.
 * Not linked from product navigation. Figures here are sample strings.
 */

import { useState } from "react";
import { ReportSetupForm, type ReportSetupWrite } from "@/components/statutory/ReportSetupForm";
import { StatutoryLoadError } from "@/components/statutory/StatutoryLoadError";
import { WorkspaceSidebar } from "@/components/statutory/WorkspaceSidebar";
import { displayAmount, type RoundingMode } from "@/lib/report-display";
import {
  activeSection,
  sectionIsOn,
  sectionsForFramework,
  type ReportingFramework,
  type WorkspaceSection,
} from "@/lib/workspace-sections";

function section(
  id: string,
  label: string,
  group: string,
  groupLabel: string,
  order: number,
): WorkspaceSection {
  return { id, label, group, group_label: groupLabel, order };
}

const STORED = "18400.40";

const FRAMEWORKS: ReportingFramework[] = [
  {
    id: "frs102-1a-ie",
    label: "FRS 102 Section 1A (Ireland)",
    available: true,
    sections: [
      section("review", "Review dashboard", "overview", "Overview", 1),
      section("report-setup", "Report setup", "report-options", "Report options", 2),
      section("sub-lines", "Mapping", "inputs", "Inputs", 3),
      section("adjustments", "Adjustments", "inputs", "Inputs", 4),
      section("disclosures", "Disclosures", "inputs", "Inputs", 5),
      section("company-details", "Company details", "inputs", "Inputs", 6),
      {
        id: "income",
        label: "Income statement",
        group: "sections",
        group_label: "Sections",
        order: 7,
        lock: "locked",
        default: "on",
        built: true,
      },
      {
        id: "oci",
        label: "Statement of comprehensive income",
        group: "sections",
        group_label: "Sections",
        order: 8,
        lock: "user",
        default: "engine",
        built: false,
      },
      {
        id: "sofp",
        label: "Statement of financial position",
        group: "sections",
        group_label: "Sections",
        order: 9,
        lock: "locked",
        default: "on",
        built: true,
      },
      {
        id: "socie",
        label: "Statement of changes in equity",
        group: "sections",
        group_label: "Sections",
        order: 10,
        lock: "user",
        default: "engine",
        built: false,
      },
      {
        id: "cash-flow",
        label: "Cash flow statement",
        group: "sections",
        group_label: "Sections",
        order: 11,
        lock: "user",
        default: "off",
        built: false,
      },
      {
        id: "trading",
        label: "Supplementary trading statement",
        group: "sections",
        group_label: "Sections",
        order: 12,
        lock: "user",
        default: "off",
        built: false,
      },
      {
        id: "cover",
        label: "Cover",
        group: "sections",
        group_label: "Sections",
        order: 13,
        lock: "user",
        default: "on",
        built: true,
      },
      {
        id: "draft-pdf",
        label: "Draft PDF",
        group: "outputs",
        group_label: "Outputs",
        order: 14,
      },
    ],
  },
  {
    id: "form11-summary",
    label: "Sole Trader / Form 11 Summary",
    available: false,
    sections: [
      section("review", "Review dashboard", "overview", "Overview", 1),
      section("report-setup", "Report setup", "report-options", "Report options", 2),
    ],
  },
];

const SETUP = {
  basis_id: "frs102-1a-ie",
  basis_version: "2024.09",
  basis_label: "FRS 102 Section 1A (Ireland)",
  rounding: "unit" as const,
  statement_type: "draft" as const,
  face_dates: {
    current_start: "2026-01-01",
    current_end: "2026-12-31",
    prior_start: null,
    prior_end: null,
  },
  column_headers: {
    as_at_current: "2026",
    as_at_prior: "2025",
    ended_current: "2026",
    ended_prior: "2025",
  },
  trial_balance_period_start: "2026-01-01",
  trial_balance_period_end: "2026-12-31",
};

export default function StatutoryWorkspacePreviewPage() {
  const [frameworkId, setFrameworkId] = useState("frs102-1a-ie");
  const [requested, setRequested] = useState<string | null>("review");
  const [rounding, setRounding] = useState<RoundingMode>("unit");
  const [header, setHeader] = useState("2026");
  const [saved, setSaved] = useState<string>("Nothing saved");
  const [flags, setFlags] = useState<Record<string, boolean>>({});
  const sections = sectionsForFramework(FRAMEWORKS, frameworkId).map((item) =>
    item.lock ? { ...item, enabled: sectionIsOn(item, flags) } : item,
  );
  const sectionId = activeSection(sections, requested);
  const activeMeta = sections.find((item) => item.id === sectionId);

  function onToggle(id: string, enabled: boolean): void {
    setFlags((current) => ({ ...current, [id]: enabled }));
  }

  function onSave(next: ReportSetupWrite): void {
    setRounding(next.rounding);
    setHeader(next.column_headers.ended_current);
    setSaved(JSON.stringify(next));
  }

  return (
    <main className="mx-auto flex max-w-5xl items-start gap-6 p-6">
      <div className="space-y-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          Preview framework
          <select
            data-testid="preview-framework"
            value={frameworkId}
            onChange={(event) => {
              setFrameworkId(event.target.value);
              setRequested(null);
              setFlags({});
            }}
            className="rounded-md border border-line bg-surface-elevated px-3 py-2"
          >
            <option value="frs102-1a-ie">FRS 102</option>
            <option value="form11-summary">Form 11 Summary</option>
            <option value="uk-frs105">Unknown framework</option>
          </select>
        </label>
        <WorkspaceSidebar
          sections={sections}
          activeId={sectionId}
          onSelect={setRequested}
          onToggle={onToggle}
        />
      </div>
      <div className="min-w-0 flex-1 space-y-6">
        <h1 className="text-xl font-medium text-ink">Statutory workspace preview</h1>
        <StatutoryLoadError
          testId="statutory-statements-error"
          message="Product 1 line 'operating_expenses' on 'Operating Expenses' needs a statutory sub-line"
          onReview={() => setRequested("sub-lines")}
        />
        <p className="text-sm text-ink-secondary" data-testid="preview-section">
          Open section: {sectionId}. Sidebar entries: {sections.map((section) => section.label).join(", ")}.
        </p>
        {sectionId === "draft-pdf" ? (
          <section className="space-y-3" data-testid="statutory-outputs">
            <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
              Outputs
            </h2>
            <button
              type="button"
              data-testid="statutory-download"
              disabled
              className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50"
            >
              Download draft PDF
            </button>
            <p className="text-sm text-ink-secondary" data-testid="statutory-download-reason">
              This preview does not call the API.
            </p>
          </section>
        ) : null}
        {activeMeta?.lock != null && sectionId !== "income" && sectionId !== "sofp" ? (
          <section className="space-y-2" data-testid="statutory-section-panel">
            <h2 className="text-sm font-semibold text-ink">{activeMeta.label}</h2>
            {activeMeta.enabled === false ? (
              <p className="text-sm text-ink-secondary">
                This section is off. Its data is kept.
              </p>
            ) : activeMeta.built === false ? (
              <p className="text-sm text-ink-secondary">
                [NOT BUILT: this pack does not build this statement]
              </p>
            ) : (
              <p className="text-sm text-ink-secondary">
                This section is included in the draft PDF.
              </p>
            )}
          </section>
        ) : null}
        {sectionId === "report-setup" ? (
          <ReportSetupForm
            frameworks={FRAMEWORKS}
            setup={SETUP}
            busy={false}
            onSave={onSave}
          />
        ) : null}
        <p className="text-sm" data-testid="preview-saved">
          {saved}
        </p>
        <table className="text-sm">
          <thead>
            <tr>
              <th className="px-3 py-2 text-left">Line</th>
              <th className="px-3 py-2 text-right" data-testid="preview-header">
                {header}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="px-3 py-2">Net assets</td>
              <td
                className="px-3 py-2 text-right tabular-nums"
                data-testid="preview-amount"
                data-stored={STORED}
              >
                {displayAmount(STORED, rounding)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </main>
  );
}
