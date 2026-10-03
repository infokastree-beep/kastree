"use client";

/**
 * Auth-free preview of the statutory sidebar and display-only report setup.
 * Not linked from product navigation. Figures here are sample strings.
 */

import { useState } from "react";
import { ReportSetupForm, type ReportSetupWrite } from "@/components/statutory/ReportSetupForm";
import { WorkspaceSidebar } from "@/components/statutory/WorkspaceSidebar";
import { displayAmount, type RoundingMode } from "@/lib/report-display";
import {
  activeSection,
  sectionsForFramework,
  type ReportingFramework,
} from "@/lib/workspace-sections";

const STORED = "18400.40";

const FRAMEWORKS: ReportingFramework[] = [
  {
    id: "frs102-1a-ie",
    label: "FRS 102 Section 1A (Ireland)",
    available: true,
    sections: [
      { id: "report-setup", label: "Report setup" },
      { id: "sub-lines", label: "Sub-line review" },
      { id: "disclosures", label: "Disclosures" },
      { id: "adjustments", label: "Adjustments" },
      { id: "review", label: "Review dashboard" },
      { id: "income", label: "Income statement" },
      { id: "sofp", label: "Statement of financial position" },
    ],
  },
  {
    id: "form11-summary",
    label: "Sole Trader / Form 11 Summary",
    available: false,
    sections: [
      { id: "report-setup", label: "Report setup" },
      { id: "extracts", label: "Extracts summary" },
      { id: "review", label: "Review dashboard" },
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
  const sections = sectionsForFramework(FRAMEWORKS, frameworkId);
  const sectionId = activeSection(sections, requested);

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
        />
      </div>
      <div className="min-w-0 flex-1 space-y-6">
        <h1 className="text-xl font-medium text-ink">Statutory workspace preview</h1>
        <p className="text-sm text-ink-secondary" data-testid="preview-section">
          Open section: {sectionId}. Sidebar entries: {sections.map((section) => section.label).join(", ")}.
        </p>
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
