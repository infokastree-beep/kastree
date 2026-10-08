"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { downloadDraftPdf, pdfBlockReason } from "@/lib/draft-pdf";
import { messageFromPdfBody } from "@/lib/workspace-load-error";
import {
  CompanyDetailsForm,
  type ApprovalWrite,
  type CompanyDetails,
  type CompanyDetailsWrite,
} from "@/components/statutory/CompanyDetailsForm";
import {
  ReportSetupForm,
  type ReportSetup,
  type ReportSetupWrite,
} from "@/components/statutory/ReportSetupForm";
import { SectionsSetup } from "@/components/statutory/SectionsSetup";
import { StatutoryLoadError } from "@/components/statutory/StatutoryLoadError";
import { StatutorySublineReview } from "@/components/statutory/StatutorySublineReview";
import { WorkspaceSidebar } from "@/components/statutory/WorkspaceSidebar";
import { displayAmount, type RoundingMode } from "@/lib/report-display";
import {
  activeSection,
  navigatorSections,
  sectionIsOn,
  sectionsForFramework,
  type ReportingFramework,
} from "@/lib/workspace-sections";

const SIGNOFF =
  "Draft statutory packs stay limited to platform administrators until a qualified reviewer signs off the wording.";

type UserMe = {
  role: "owner" | "admin" | "member" | "viewer";
  is_platform_admin: boolean;
};

type YearEnd = {
  id: string;
  company_id: string;
  period_start: string | null;
  period_end: string;
  pack_id: string;
  pack_version: string;
  prior_year_validated: boolean;
  first_financial_period: boolean;
  adopted_trial_balance_id: string | null;
};

type WorkingDraft = {
  draft_id: string;
  version_number: number;
  status: string;
  row_version: number;
  tb_version_id: string | null;
  mapping_notice: string | null;
  frozen: boolean;
};

type DashboardCheck = {
  code: string;
  severity: string;
  passed: boolean;
  message: string;
};

type DraftDashboard = {
  draft_id: string;
  status: string;
  row_version: number;
  traffic: "red" | "amber" | "green";
  can_finalise: boolean;
  unanswered_disclosures: string[];
  checks: DashboardCheck[];
};

type StatementRow = {
  label: string;
  current: string;
  prior: string | null;
};

type StatementPack = {
  watermark: string;
  renderable: boolean;
  blocked: boolean;
  build_error: string | null;
  checks: DashboardCheck[];
  net_assets: string | null;
  profit: string | null;
  company_name: string;
  sofp: StatementRow[];
  income: StatementRow[];
};

type AdjustmentLine = {
  nominal_code: string;
  account_name: string;
  canonical_line: string;
  debit: string;
  credit: string;
};

const EMPTY_LINE: AdjustmentLine = {
  nominal_code: "",
  account_name: "",
  canonical_line: "",
  debit: "",
  credit: "",
};

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return messageFromPdfBody(error.body) ?? error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong";
}

function saveMessage(error: unknown, fallback: string): string {
  const text = messageFrom(error);
  if (text.trim().length === 0 || /^API \d+$/.test(text)) {
    return fallback;
  }
  return text;
}

function flagLabel(flag: string): string {
  return flag
    .toLowerCase()
    .split("_")
    .map((word) => (word.length > 0 ? word[0]!.toUpperCase() + word.slice(1) : word))
    .join(" ");
}

function trafficClass(traffic: DraftDashboard["traffic"]): string {
  if (traffic === "green") {
    return "border-emerald-200 bg-emerald-50 text-emerald-950";
  }
  if (traffic === "amber") {
    return "border-amber-200 bg-amber-50 text-amber-950";
  }
  return "border-red-200 bg-red-50 text-red-950";
}

async function absentOn404<T>(path: string, getToken: () => Promise<string | null>): Promise<T | null> {
  try {
    return await apiFetch<T>(path, { getToken });
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 404) {
      return null;
    }
    throw caught;
  }
}

export function StatutoryDraftWorkspace({ yearEndId }: { yearEndId: string }) {
  const { getToken, isSignedIn } = useAuth();
  const queryClient = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [companyError, setCompanyError] = useState<string | null>(null);
  const [companySaved, setCompanySaved] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [approvalSaved, setApprovalSaved] = useState<string | null>(null);
  const [narration, setNarration] = useState("");
  const [lines, setLines] = useState<AdjustmentLine[]>([
    { ...EMPTY_LINE },
    { ...EMPTY_LINE },
  ]);

  const meQuery = useQuery({
    queryKey: ["users", "me"],
    queryFn: () => apiFetch<UserMe>("/users/me", { getToken }),
    enabled: isSignedIn,
  });
  const yearEndQuery = useQuery({
    queryKey: ["year-end", yearEndId],
    queryFn: () => apiFetch<YearEnd>(`/year-ends/${yearEndId}`, { getToken }),
    enabled: isSignedIn && meQuery.data?.is_platform_admin === true,
  });
  const draftQuery = useQuery({
    queryKey: ["working-draft", yearEndId],
    queryFn: () =>
      absentOn404<WorkingDraft>(`/year-ends/${yearEndId}/draft`, getToken),
    enabled: yearEndQuery.isSuccess,
  });
  const draft = draftQuery.data ?? null;
  const dashboardQuery = useQuery({
    queryKey: ["draft-dashboard", yearEndId, draft?.draft_id],
    queryFn: () =>
      apiFetch<DraftDashboard>(
        `/year-ends/${yearEndId}/drafts/${draft?.draft_id}/dashboard`,
        { getToken },
      ),
    enabled: draft !== null,
  });
  const linesQuery = useQuery({
    queryKey: ["canonical-lines"],
    queryFn: () =>
      apiFetch<{ lines: string[] }>("/year-ends/canonical-lines", { getToken }),
    enabled: draft !== null && draft.status === "draft",
  });
  const yearEnd = yearEndQuery.data;
  const statementsPath =
    yearEnd?.adopted_trial_balance_id != null
      ? `/year-ends/${yearEndId}/adopted-trial-balance/statements`
      : draft?.tb_version_id != null
        ? `/year-ends/${yearEndId}/trial-balance-versions/${draft.tb_version_id}/statements`
        : null;
  const statementsQuery = useQuery({
    queryKey: ["statutory-pack", statementsPath],
    queryFn: () => apiFetch<StatementPack>(statementsPath ?? "", { getToken }),
    enabled: statementsPath !== null,
  });
  const frameworksQuery = useQuery({
    queryKey: ["reporting-frameworks"],
    queryFn: () =>
      apiFetch<{ frameworks: ReportingFramework[] }>("/year-ends/frameworks", {
        getToken,
      }),
    enabled: isSignedIn && meQuery.data?.is_platform_admin === true,
  });
  const setupQuery = useQuery({
    queryKey: ["report-setup", yearEndId],
    queryFn: () =>
      apiFetch<ReportSetup>(`/year-ends/${yearEndId}/report-setup`, { getToken }),
    enabled: yearEndQuery.isSuccess,
  });
  const detailsQuery = useQuery({
    queryKey: ["company-details", yearEndId],
    queryFn: () =>
      apiFetch<CompanyDetails>(`/year-ends/${yearEndId}/company-details`, {
        getToken,
      }),
    enabled: yearEndQuery.isSuccess,
  });

  const forbidden = meQuery.data?.is_platform_admin === false;
  const dashboard = dashboardQuery.data;
  const writable = draft?.status === "draft" && !draft.frozen && busy === null;
  const priorYearBlocked =
    statementsQuery.data?.checks.some(
      (check) => check.code === "V-GATE-001" && !check.passed,
    ) ?? false;

  const canEditDetails =
    meQuery.data?.role === "owner" ||
    meQuery.data?.role === "admin" ||
    meQuery.data?.role === "member";

  async function saveCompany(next: CompanyDetailsWrite): Promise<void> {
    setCompanyError(null);
    setCompanySaved(null);
    setBusy("Saving company details…");
    try {
      const saved = await apiFetch<CompanyDetails>(
        `/year-ends/${yearEndId}/company-details`,
        {
          method: "PUT",
          getToken,
          body: JSON.stringify(next),
        },
      );
      queryClient.setQueryData(["company-details", yearEndId], saved);
      setCompanySaved("Company details saved.");
      await queryClient.invalidateQueries({ queryKey: ["statutory-pack"] });
      await queryClient.invalidateQueries({ queryKey: ["draft-dashboard", yearEndId] });
    } catch (caught) {
      setCompanyError(saveMessage(caught, "Company details could not be saved."));
    } finally {
      setBusy(null);
    }
  }

  async function saveApproval(next: ApprovalWrite): Promise<void> {
    setApprovalError(null);
    setApprovalSaved(null);
    setBusy("Saving approval details…");
    try {
      const saved = await apiFetch<CompanyDetails>(
        `/year-ends/${yearEndId}/approval`,
        {
          method: "PUT",
          getToken,
          body: JSON.stringify(next),
        },
      );
      queryClient.setQueryData(["company-details", yearEndId], saved);
      setApprovalSaved("Approval details saved.");
      await queryClient.invalidateQueries({ queryKey: ["statutory-pack"] });
      await queryClient.invalidateQueries({ queryKey: ["draft-dashboard", yearEndId] });
    } catch (caught) {
      setApprovalError(saveMessage(caught, "Approval details could not be saved."));
    } finally {
      setBusy(null);
    }
  }

  async function saveReportSetup(next: ReportSetupWrite): Promise<void> {
    setError(null);
    setBusy("Saving report setup…");
    try {
      const saved = await apiFetch<ReportSetup>(
        `/year-ends/${yearEndId}/report-setup`,
        {
          method: "PUT",
          getToken,
          body: JSON.stringify(next),
        },
      );
      queryClient.setQueryData(["report-setup", yearEndId], saved);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  function selectSection(sectionId: string): void {
    router.replace(`/year-ends/${yearEndId}/draft?section=${sectionId}`);
  }

  async function toggleSection(sectionId: string, enabled: boolean): Promise<void> {
    const setup = setupQuery.data;
    if (setup == null) {
      return;
    }
    await saveReportSetup({
      rounding: setup.rounding,
      statement_type: setup.statement_type,
      face_dates: setup.face_dates,
      column_headers: setup.column_headers,
      sections: { ...(setup.sections ?? {}), [sectionId]: enabled },
    });
  }

  async function refreshDraft(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["working-draft", yearEndId] });
    await queryClient.invalidateQueries({ queryKey: ["draft-dashboard", yearEndId] });
    await queryClient.invalidateQueries({ queryKey: ["statutory-pack"] });
    await queryClient.invalidateQueries({ queryKey: ["year-end", yearEndId] });
  }

  async function answerDisclosure(flagName: string, answer: "yes" | "no"): Promise<void> {
    if (!draft || !dashboard) {
      return;
    }
    setError(null);
    setBusy("Saving disclosure answer…");
    try {
      await apiFetch(
        `/year-ends/${yearEndId}/drafts/${draft.draft_id}/disclosures`,
        {
          method: "POST",
          getToken,
          body: JSON.stringify({
            row_version: dashboard.row_version,
            flag_name: flagName,
            answer,
          }),
        },
      );
      await refreshDraft();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  async function postAdjustment(): Promise<void> {
    if (!draft || !dashboard) {
      return;
    }
    setError(null);
    setBusy("Posting adjustment…");
    try {
      await apiFetch(
        `/year-ends/${yearEndId}/drafts/${draft.draft_id}/adjustments`,
        {
          method: "POST",
          getToken,
          headers: { "Idempotency-Key": crypto.randomUUID() },
          body: JSON.stringify({
            row_version: dashboard.row_version,
            narration,
            lines,
          }),
        },
      );
      setNarration("");
      setLines([{ ...EMPTY_LINE }, { ...EMPTY_LINE }]);
      await refreshDraft();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  async function lockDraft(): Promise<void> {
    if (!draft || !dashboard) {
      return;
    }
    setError(null);
    setBusy("Locking this draft…");
    try {
      await apiFetch(`/year-ends/${yearEndId}/drafts/${draft.draft_id}/lock`, {
        method: "POST",
        getToken,
        body: JSON.stringify({ row_version: dashboard.row_version }),
      });
      await refreshDraft();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  async function acknowledgeMappings(): Promise<void> {
    if (!draft || !dashboard) {
      return;
    }
    setError(null);
    setBusy("Acknowledging the current mappings…");
    try {
      await apiFetch(
        `/year-ends/${yearEndId}/drafts/${draft.draft_id}/acknowledge-mappings`,
        {
          method: "POST",
          getToken,
          body: JSON.stringify({ row_version: dashboard.row_version }),
        },
      );
      await refreshDraft();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  async function startNewReport(): Promise<void> {
    if (!draft || !dashboard) {
      return;
    }
    setError(null);
    setBusy("Starting a new statutory report…");
    try {
      await apiFetch(
        `/year-ends/${yearEndId}/drafts/${draft.draft_id}/new-report`,
        {
          method: "POST",
          getToken,
          body: JSON.stringify({ row_version: dashboard.row_version }),
        },
      );
      await refreshDraft();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  async function newVersion(): Promise<void> {
    if (!draft || !dashboard) {
      return;
    }
    setError(null);
    setBusy("Opening the next draft version…");
    try {
      await apiFetch(
        `/year-ends/${yearEndId}/drafts/${draft.draft_id}/new-version`,
        {
          method: "POST",
          getToken,
          body: JSON.stringify({ row_version: dashboard.row_version }),
        },
      );
      await refreshDraft();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  async function markFirstPeriod(): Promise<void> {
    setError(null);
    setBusy("Opening the first-period gate…");
    try {
      await apiFetch(`/year-ends/${yearEndId}/first-financial-period`, {
        method: "POST",
        getToken,
      });
      await refreshDraft();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  const pdfReason = pdfBlockReason({
    statementsError: statementsQuery.error
      ? messageFrom(statementsQuery.error)
      : null,
    dashboardError: dashboardQuery.error ? messageFrom(dashboardQuery.error) : null,
    renderable: statementsQuery.data?.renderable ?? null,
    checks: statementsQuery.data?.checks ?? dashboard?.checks ?? [],
  });
  const pdfPath =
    yearEnd?.adopted_trial_balance_id != null
      ? `/year-ends/${yearEndId}/adopted-trial-balance/statements.pdf`
      : draft?.tb_version_id != null
        ? `/year-ends/${yearEndId}/trial-balance-versions/${draft.tb_version_id}/statements.pdf`
        : null;

  async function downloadPdf(): Promise<void> {
    if (pdfReason !== null || statementsQuery.data?.renderable !== true || pdfPath === null) {
      return;
    }
    setError(null);
    setBusy("Preparing PDF…");
    try {
      await downloadDraftPdf(pdfPath, getToken);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  function updateLine(index: number, patch: Partial<AdjustmentLine>): void {
    setLines((current) =>
      current.map((line, lineIndex) =>
        lineIndex === index ? { ...line, ...patch } : line,
      ),
    );
  }

  if (!isSignedIn) {
    return <p className="text-sm text-ink-secondary">Sign in to continue.</p>;
  }
  if (meQuery.isLoading || yearEndQuery.isLoading) {
    return <p className="text-sm text-soft">Loading the statutory workspace…</p>;
  }
  if (forbidden) {
    return (
      <p className="text-sm text-ink-secondary" data-testid="statutory-draft-signoff">
        {SIGNOFF}
      </p>
    );
  }
  if (meQuery.error || yearEndQuery.error || !yearEnd) {
    return (
      <p
        className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
        data-testid="statutory-draft-error"
      >
        {messageFrom(meQuery.error ?? yearEndQuery.error ?? "Year end not found")}
      </p>
    );
  }

  const period =
    yearEnd.period_start != null
      ? `${yearEnd.period_start} to ${yearEnd.period_end}`
      : `period ending ${yearEnd.period_end}`;
  const savedFlags = setupQuery.data?.sections ?? null;
  const sections = sectionsForFramework(
    frameworksQuery.data?.frameworks ?? [],
    yearEnd.pack_id,
  ).map((section) =>
    section.lock
      ? { ...section, enabled: sectionIsOn(section, savedFlags) }
      : section,
  );
  const sectionId = activeSection(sections, searchParams.get("section"));
  const activeMeta = sections.find((section) => section.id === sectionId);
  const rounding: RoundingMode = setupQuery.data?.rounding ?? "unit";
  const headers = setupQuery.data?.column_headers;

  return (
    <div className="flex items-start gap-6" data-testid="statutory-draft-workspace">
      <WorkspaceSidebar
        sections={navigatorSections(sections)}
        activeId={sectionId}
        onSelect={selectSection}
      />
      <div className="min-w-0 flex-1 space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Statutory workspace
          </p>
          <h1 className="font-display text-heading-md text-ink">
            {statementsQuery.data?.company_name || "Statutory draft"}
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-secondary">
            {period}. Pack {yearEnd.pack_id} {yearEnd.pack_version}. This page
            stays at this address, so you can leave and come back to the same
            draft.
          </p>
        </div>
        {yearEnd.adopted_trial_balance_id ? (
          <Link
            href={`/dashboard/${yearEnd.adopted_trial_balance_id}/statements?tab=Statutory`}
            className="text-sm font-medium text-accent underline-offset-2 hover:underline"
          >
            Back to statements
          </Link>
        ) : null}
      </div>

      {error ? (
        <p
          className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
          data-testid="statutory-draft-error"
        >
          {error}
        </p>
      ) : null}
      {busy ? <p className="text-sm text-soft">{busy}</p> : null}
      {draftQuery.error ? (
        <p className="text-sm text-red-800">{messageFrom(draftQuery.error)}</p>
      ) : null}
      {dashboardQuery.error ? (
        <StatutoryLoadError
          testId="statutory-dashboard-error"
          message={messageFrom(dashboardQuery.error)}
          onReview={() => selectSection("sub-lines")}
        />
      ) : null}
      {statementsQuery.error ? (
        <StatutoryLoadError
          testId="statutory-statements-error"
          message={messageFrom(statementsQuery.error)}
          onReview={() => selectSection("sub-lines")}
        />
      ) : null}

      {draft?.mapping_notice ? (
        <section
          className="space-y-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950"
          data-testid="statutory-mapping-notice"
        >
          <p>{draft.mapping_notice}</p>
          <button
            type="button"
            disabled={busy !== null || !dashboard}
            onClick={() => void acknowledgeMappings()}
            className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
            data-testid="statutory-acknowledge-mappings"
          >
            Acknowledge
          </button>
        </section>
      ) : null}

      {draft === null && draftQuery.isSuccess ? (
        <section
          className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950"
          data-testid="statutory-draft-missing"
        >
          <p className="font-medium">No working draft is stored for this year end yet.</p>
          <p className="mt-1">
            Adjustments, disclosure answers, and locking belong to a statutory
            trial-balance version. Continuing from a Product 1 trial balance
            keeps that trial balance and does not create one. The adopted pack
            below reloads whenever you open this page.
          </p>
        </section>
      ) : null}

      {priorYearBlocked ? (
        <div
          className="space-y-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950"
          data-testid="statutory-first-period-gate"
        >
          <p>Prior-year comparatives are still required before this draft can show figures.</p>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void markFirstPeriod()}
            className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
          >
            This is the first financial period
          </button>
        </div>
      ) : null}

      {sectionId === "sections-setup" ? (
        <SectionsSetup
          title={activeMeta?.label ?? ""}
          sections={sections}
          onToggle={(id, enabled) => void toggleSection(id, enabled)}
          togglesEnabled={canEditDetails && setupQuery.isSuccess && busy === null}
        />
      ) : null}

      {sectionId === "draft-pdf" ? (
        <section className="space-y-3" data-testid="statutory-outputs">
          <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
            Outputs
          </h2>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              data-testid="statutory-download"
              disabled={
                busy !== null ||
                pdfReason !== null ||
                statementsQuery.data?.renderable !== true
              }
              onClick={() => void downloadPdf()}
              className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50"
            >
              Download draft PDF
            </button>
            {pdfReason !== null ? (
              <p className="text-sm text-ink-secondary" data-testid="statutory-download-reason">
                {pdfReason}
              </p>
            ) : null}
          </div>
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

      {sectionId === "report-setup" && setupQuery.data ? (
        <ReportSetupForm
          key={`${setupQuery.data.rounding}-${setupQuery.data.statement_type}-${setupQuery.data.face_dates.current_end}`}
          frameworks={frameworksQuery.data?.frameworks ?? []}
          setup={setupQuery.data}
          busy={busy !== null}
          onSave={(next) => void saveReportSetup(next)}
        />
      ) : null}

      {sectionId === "sub-lines" && yearEnd.adopted_trial_balance_id ? (
        <StatutorySublineReview
          yearEndId={yearEndId}
          onConfirmed={refreshDraft}
        />
      ) : null}

      {sectionId === "company-details" && detailsQuery.error ? (
        <StatutoryLoadError
          testId="statutory-company-load-error"
          message={saveMessage(
            detailsQuery.error,
            "Company details could not be loaded.",
          )}
          onReview={() => undefined}
        />
      ) : null}

      {sectionId === "company-details" && detailsQuery.data ? (
        <CompanyDetailsForm
          key={JSON.stringify(detailsQuery.data)}
          details={detailsQuery.data}
          canEdit={canEditDetails}
          busy={busy !== null}
          companyError={companyError}
          companySaved={companySaved}
          approvalError={approvalError}
          approvalSaved={approvalSaved}
          onSaveCompany={(next) => void saveCompany(next)}
          onSaveApproval={(next) => void saveApproval(next)}
        />
      ) : null}

      {sectionId === "review" && dashboard ? (
        <section
          className={`rounded-md border px-4 py-3 ${trafficClass(dashboard.traffic)}`}
          data-testid="statutory-review-dashboard"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.12em]">
            Review dashboard
          </p>
          <p className="mt-1 text-lg font-semibold capitalize" data-testid="statutory-traffic">
            {dashboard.traffic}
          </p>
          <p className="mt-1 text-sm">
            Draft version {draft?.version_number}. Status {dashboard.status}.
            {dashboard.can_finalise
              ? " Ready to finalise."
              : " Not ready to finalise."}
          </p>
          <ul className="mt-3 space-y-1 text-sm">
            {dashboard.checks
              .filter((check) => !check.passed)
              .map((check) => (
                <li key={check.code}>
                  {check.severity} {check.code}: {check.message}
                </li>
              ))}
          </ul>
        </section>
      ) : null}

      {sectionId === "disclosures" && dashboard && dashboard.unanswered_disclosures.length > 0 ? (
        <section className="space-y-3" data-testid="statutory-disclosures">
          <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
            Disclosure questions
          </h2>
          <ul className="space-y-2">
            {dashboard.unanswered_disclosures.map((flag) => (
              <li
                key={flag}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line bg-surface-elevated px-4 py-3"
              >
                <span className="text-sm text-ink">{flagLabel(flag)}</span>
                <span className="flex gap-2">
                  <button
                    type="button"
                    disabled={!writable}
                    onClick={() => void answerDisclosure(flag, "yes")}
                    className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
                  >
                    Yes
                  </button>
                  <button
                    type="button"
                    disabled={!writable}
                    onClick={() => void answerDisclosure(flag, "no")}
                    className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
                  >
                    No
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {sectionId === "adjustments" && draft?.status === "draft" && dashboard ? (
        <section className="space-y-3" data-testid="statutory-adjustment">
          <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
            Post an adjustment
          </h2>
          <p className="max-w-3xl text-sm text-ink-secondary">
            A balanced journal on this draft. It does not change the trial
            balance file.
          </p>
          <label className="flex max-w-xl flex-col gap-1.5 text-sm">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
              Narration
            </span>
            <input
              value={narration}
              onChange={(event) => setNarration(event.target.value)}
              className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink"
              data-testid="statutory-adjustment-narration"
            />
          </label>
          <div className="space-y-3">
            {lines.map((line, index) => (
              <div
                key={index}
                className="grid gap-2 rounded-md border border-line bg-surface-elevated p-3 sm:grid-cols-5"
              >
                <input
                  aria-label={`Line ${index + 1} code`}
                  placeholder="Code"
                  value={line.nominal_code}
                  onChange={(event) =>
                    updateLine(index, { nominal_code: event.target.value })
                  }
                  className="rounded-md border border-line px-3 py-2 text-sm"
                />
                <input
                  aria-label={`Line ${index + 1} name`}
                  placeholder="Account name"
                  value={line.account_name}
                  onChange={(event) =>
                    updateLine(index, { account_name: event.target.value })
                  }
                  className="rounded-md border border-line px-3 py-2 text-sm"
                />
                <select
                  aria-label={`Line ${index + 1} statutory line`}
                  value={line.canonical_line}
                  onChange={(event) =>
                    updateLine(index, { canonical_line: event.target.value })
                  }
                  className="rounded-md border border-line px-3 py-2 text-sm"
                >
                  <option value="">Statutory line</option>
                  {(linesQuery.data?.lines ?? []).map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
                <input
                  aria-label={`Line ${index + 1} debit`}
                  placeholder="Debit"
                  value={line.debit}
                  onChange={(event) => updateLine(index, { debit: event.target.value })}
                  className="rounded-md border border-line px-3 py-2 text-sm"
                />
                <input
                  aria-label={`Line ${index + 1} credit`}
                  placeholder="Credit"
                  value={line.credit}
                  onChange={(event) =>
                    updateLine(index, { credit: event.target.value })
                  }
                  className="rounded-md border border-line px-3 py-2 text-sm"
                />
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={!writable || narration.trim().length === 0}
              onClick={() => void postAdjustment()}
              className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground disabled:opacity-50"
              data-testid="statutory-adjustment-post"
            >
              Post adjustment
            </button>
            <button
              type="button"
              disabled={!writable}
              onClick={() => void lockDraft()}
              className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
              data-testid="statutory-lock"
            >
              Lock draft
            </button>
          </div>
        </section>
      ) : null}

      {sectionId === "adjustments" && draft?.status === "locked" && draft.tb_version_id !== null && dashboard ? (
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void newVersion()}
          className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
          data-testid="statutory-new-version"
        >
          Open the next draft version
        </button>
      ) : null}

      {sectionId === "adjustments" && draft && draft.tb_version_id === null && !draft.frozen && dashboard ? (
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void startNewReport()}
          className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
          data-testid="statutory-new-report"
        >
          Start a new statutory report
        </button>
      ) : null}

      {statementsQuery.data ? (
        <section className="space-y-4" data-testid="statutory-draft-pack">
          <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-amber-800">
            {statementsQuery.data.watermark} statutory pack
          </h2>
          <p className="text-sm text-ink-secondary">
            Net assets {statementsQuery.data.net_assets ?? "—"}. Profit{" "}
            {statementsQuery.data.profit ?? "—"}.
            {statementsQuery.data.renderable ? " Renderable." : " Not renderable."}
          </p>
          {statementsQuery.data.build_error ? (
            <p className="text-sm text-red-800">{statementsQuery.data.build_error}</p>
          ) : null}
          {statementsQuery.data.checks.some((check) => !check.passed) ? (
            <ul className="list-disc space-y-1 pl-5 text-sm text-ink-secondary">
              {statementsQuery.data.checks
                .filter((check) => !check.passed)
                .map((check) => (
                  <li key={check.code}>
                    {check.severity} {check.code}: {check.message}
                  </li>
                ))}
            </ul>
          ) : null}
          {sectionId === "income" ? (
            <FaceTable
              title="Income statement"
              rows={statementsQuery.data.income}
              currentHeader={headers?.ended_current ?? "Current"}
              priorHeader={headers?.ended_prior ?? "Prior"}
              rounding={rounding}
            />
          ) : null}
          {sectionId === "sofp" ? (
            <FaceTable
              title="Statement of financial position"
              rows={statementsQuery.data.sofp}
              currentHeader={headers?.as_at_current ?? "Current"}
              priorHeader={headers?.as_at_prior ?? "Prior"}
              rounding={rounding}
            />
          ) : null}
        </section>
      ) : null}
      </div>
    </div>
  );
}

function FaceTable({
  title,
  rows,
  currentHeader,
  priorHeader,
  rounding,
}: {
  title: string;
  rows: StatementRow[];
  currentHeader: string;
  priorHeader: string;
  rounding: RoundingMode;
}) {
  if (rows.length === 0) {
    return null;
  }
  return (
    <div className="overflow-x-auto rounded-md border border-line bg-surface-elevated">
      <h3 className="border-b border-line px-4 py-3 text-sm font-semibold text-ink">
        {title}
      </h3>
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-line text-xs uppercase tracking-[0.12em] text-soft">
          <tr>
            <th className="px-4 py-3 font-semibold">Line</th>
            <th className="px-4 py-3 text-right font-semibold">{currentHeader}</th>
            <th className="px-4 py-3 text-right font-semibold">{priorHeader}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-b border-line/70">
              <td className="px-4 py-2.5">{row.label}</td>
              <td
                className="px-4 py-2.5 text-right tabular-nums"
                data-stored={row.current}
              >
                {displayAmount(row.current, rounding)}
              </td>
              <td
                className="px-4 py-2.5 text-right tabular-nums"
                data-stored={row.prior ?? ""}
              >
                {row.prior === null ? "—" : displayAmount(row.prior, rounding)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
