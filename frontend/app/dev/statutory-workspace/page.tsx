"use client";

/**
 * Auth-free preview of the statutory sidebar and display-only report setup.
 * Not linked from product navigation. Figures here are sample strings.
 */

import { useState } from "react";
import { ReportSetupForm, type ReportSetupWrite } from "@/components/statutory/ReportSetupForm";
import { SectionPreview } from "@/components/statutory/SectionPreview";
import { SectionsSetup } from "@/components/statutory/SectionsSetup";
import { StatutoryLoadError } from "@/components/statutory/StatutoryLoadError";
import { WorkspaceSidebar } from "@/components/statutory/WorkspaceSidebar";
import { displayAmount, type RoundingMode } from "@/lib/report-display";
import {
  scrollAnchorFor,
  showsPageNumberNote,
  type PreviewChild,
} from "@/lib/section-preview";
import {
  activeSection,
  navigatorSections,
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
      section("sections-setup", "Sections setup", "sections", "Sections", 7),
      {
        id: "income",
        label: "Income statement",
        group: "sections",
        group_label: "Sections",
        order: 8,
        lock: "locked",
        default: "on",
        built: true,
        new_page: true,
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
        new_page: true,
      },
      {
        id: "contents",
        label: "Contents",
        group: "sections",
        group_label: "Sections",
        order: 10,
        lock: "user",
        default: "on",
        built: true,
        new_page: true,
      },
      {
        id: "notes",
        label: "Notes",
        group: "sections",
        group_label: "Sections",
        order: 11,
        lock: "locked",
        default: "on",
        built: true,
        new_page: true,
      },
      {
        id: "compilation",
        label: "Compilation report",
        group: "sections",
        group_label: "Sections",
        order: 12,
        lock: "user",
        default: "on",
        built: true,
        new_page: true,
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
        new_page: true,
      },
      {
        id: "oci",
        label: "Statement of comprehensive income",
        group: "sections",
        group_label: "Sections",
        order: 14,
        lock: "user",
        default: "engine",
        built: false,
      },
      {
        id: "socie",
        label: "Statement of changes in equity",
        group: "sections",
        group_label: "Sections",
        order: 15,
        lock: "user",
        default: "engine",
        built: false,
      },
      {
        id: "trading",
        label: "Supplementary trading statement",
        group: "sections",
        group_label: "Sections",
        order: 16,
        lock: "user",
        default: "off",
        built: false,
      },
      {
        id: "cash-flow",
        label: "Cash flow statement",
        group: "sections",
        group_label: "Sections",
        order: 17,
        lock: "user",
        default: "off",
        built: false,
      },
      {
        id: "draft-pdf",
        label: "Draft PDF",
        group: "outputs",
        group_label: "Outputs",
        order: 18,
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

const NOTE_CHILDREN: PreviewChild[] = [
  { id: "N3_DEBTORS", number: 3, label: "Debtors", anchor: "note-N3_DEBTORS" },
];

const COMPILATION_CHILDREN: PreviewChild[] = [
  { id: "approval", number: null, label: "Approval of financial statements", anchor: "approval" },
  { id: "audit-exemption", number: null, label: "Audit exemption", anchor: "audit-exemption" },
];

const SAMPLE_HTML = `<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src 'none'; font-src 'none'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"><style>body{font-family:Georgia,serif;margin:24px}p{margin:0 0 12px} .spacer{height:900px}</style></head><body><p>DRAFT</p><h1>Sample company</h1><div class="spacer"></div><a id="note-N3_DEBTORS"></a><h2>3. Debtors</h2><p>Debtors note.</p><a id="approval"></a><h2>Approval of financial statements</h2><a id="audit-exemption"></a><h2>Audit exemption</h2></body></html>`;

const SETUP = {
  basis_id: "frs102-1a-ie",
  basis_version: "2024.09",
  basis_label: "FRS 102 Section 1A (Ireland)",
  rounding: "unit" as const,
  statement_type: "draft" as const,
  currency: "GBP",
  rounding_unit_label: "Nearest pound",
  rounding_thousands_label: "Nearest £'000",
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
  const [pageStarts, setPageStarts] = useState<Record<string, boolean>>({});
  const [noteId, setNoteId] = useState<string | null>(null);
  const sections = sectionsForFramework(FRAMEWORKS, frameworkId).map((item) =>
    item.lock ? { ...item, enabled: sectionIsOn(item, flags) } : item,
  );
  const visible = navigatorSections(sections);
  const sectionId = activeSection(sections, requested);
  const activeMeta = sections.find((item) => item.id === sectionId);
  const previewChildren =
    sectionId === "notes"
      ? NOTE_CHILDREN
      : sectionId === "compilation"
        ? COMPILATION_CHILDREN
        : [];
  const previewing =
    activeMeta?.group === "sections" &&
    activeMeta.id !== "sections-setup" &&
    activeMeta.enabled !== false &&
    activeMeta.built !== false;

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
              setNoteId(null);
              setFlags({});
              setPageStarts({});
            }}
            className="rounded-md border border-line bg-surface-elevated px-3 py-2"
          >
            <option value="frs102-1a-ie">FRS 102</option>
            <option value="form11-summary">Form 11 Summary</option>
            <option value="uk-frs105">Unknown framework</option>
          </select>
        </label>
        <WorkspaceSidebar
          sections={visible}
          activeId={sectionId}
          childrenBySection={{
            notes: NOTE_CHILDREN,
            compilation: COMPILATION_CHILDREN,
          }}
          activeChildId={noteId}
          onSelect={(id) => {
            setRequested(id);
            setNoteId(null);
          }}
          onSelectChild={(parentId, childId) => {
            setRequested(parentId);
            setNoteId(childId);
          }}
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
          Open section: {sectionId}. Sidebar entries: {visible.map((section) => section.label).join(", ")}.
        </p>
        {sectionId === "sections-setup" ? (
          <SectionsSetup
            title={activeMeta?.label ?? ""}
            sections={sections}
            onToggle={onToggle}
            pageStarts={pageStarts}
            onPageStart={(id, starts) =>
              setPageStarts((current) => ({ ...current, [id]: starts }))
            }
            togglesEnabled
            canReset
            onReset={() => {
              setFlags({});
              setPageStarts({});
              setSaved("Sections reset");
            }}
          />
        ) : null}
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
            ) : previewing ? (
              <div className="space-y-2">
                {showsPageNumberNote(sectionId) ? (
                  <p className="text-sm text-ink-secondary" data-testid="statutory-page-numbers">
                    Page numbers appear in the PDF.
                  </p>
                ) : null}
                <SectionPreview
                  html={SAMPLE_HTML}
                  scrollAnchor={scrollAnchorFor(noteId, previewChildren)}
                  title={activeMeta.label}
                />
              </div>
            ) : null}
          </section>
        ) : null}
        {sectionId === "income" || sectionId === "sofp" ? (
          <SectionPreview
            html={SAMPLE_HTML}
            scrollAnchor={null}
            title={activeMeta?.label ?? ""}
          />
        ) : null}
        {sectionId === "report-setup" ? (
          <ReportSetupForm
            frameworks={FRAMEWORKS}
            setup={SETUP}
            busy={false}
            onSave={onSave}
            canReset
            onReset={() => setSaved("Display reset")}
          />
        ) : null}
        <p className="text-sm" data-testid="preview-saved">
          {saved}
        </p>
        {previewing ? null : (
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
        )}
      </div>
    </main>
  );
}
