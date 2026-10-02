"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch, getApiBaseUrl } from "@/lib/api";
import { formatCurrency } from "@/lib/currency";
import { formatDate } from "@/lib/utils";

const FRAMEWORKS = [
  {
    packId: "frs102-1a-ie",
    packVersion: "2024.09",
    label: "FRS 102 Section 1A (Ireland)",
  },
] as const;

const SIGNOFF =
  "Draft statutory packs stay limited to platform administrators until a qualified reviewer signs off the wording.";

type UserMe = {
  is_platform_admin: boolean;
};

type CarriedMapping = {
  nominal_code: string;
  account_name: string;
  product1_line: string;
  canonical_line: string;
};

type ContinuedYearEnd = {
  year_end_id: string;
  trial_balance_id: string;
  lines: CarriedMapping[];
};

type StatementRow = {
  label: string;
  current: string;
  prior: string | null;
};

type StatementCheck = {
  code: string;
  severity: string;
  passed: boolean;
  message: string;
};

type StatementPack = {
  watermark: string;
  renderable: boolean;
  blocked: boolean;
  build_error: string | null;
  checks: StatementCheck[];
  net_assets: string | null;
  profit: string | null;
  sofp: StatementRow[];
  income: StatementRow[];
};

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong";
}

function money(amount: string | null, currency: string): string {
  if (amount === null || amount === "") {
    return "—";
  }
  return formatCurrency(amount, currency);
}

function frameworkKey(packId: string, packVersion: string): string {
  return `${packId}|${packVersion}`;
}

export function StatutoryContinuation({
  tbId,
  periodEnd,
  currencyCode,
}: {
  tbId: string;
  periodEnd: string;
  currencyCode: string;
}) {
  const { getToken, isSignedIn } = useAuth();
  const router = useRouter();
  const meQuery = useQuery({
    queryKey: ["users", "me"],
    queryFn: () => apiFetch<UserMe>("/users/me", { getToken }),
    enabled: isSignedIn,
  });
  const [framework, setFramework] = useState(
    frameworkKey(FRAMEWORKS[0].packId, FRAMEWORKS[0].packVersion),
  );
  const [yearEndId, setYearEndId] = useState<string | null>(null);
  const [carried, setCarried] = useState<CarriedMapping[]>([]);
  const [pack, setPack] = useState<StatementPack | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const selected =
    FRAMEWORKS.find(
      (item) => frameworkKey(item.packId, item.packVersion) === framework,
    ) ?? FRAMEWORKS[0];
  const priorYearBlocked =
    pack?.checks.some((check) => check.code === "V-GATE-001" && !check.passed) ??
    false;
  const forbidden = meQuery.data?.is_platform_admin === false;
  const existingYearEnd = useQuery({
    queryKey: ["statutory-year-end-link", tbId],
    queryFn: async () => {
      try {
        return await apiFetch<{ year_end_id: string }>(
          `/trial-balances/${tbId}/statutory-year-end`,
          { getToken },
        );
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 404) {
          return null;
        }
        throw caught;
      }
    },
    enabled: isSignedIn && meQuery.data?.is_platform_admin === true,
  });

  async function loadPack(nextYearEndId: string): Promise<void> {
    const statements = await apiFetch<StatementPack>(
      `/year-ends/${nextYearEndId}/adopted-trial-balance/statements`,
      { getToken },
    );
    setPack(statements);
  }

  async function generateDraft(): Promise<void> {
    setError(null);
    setBusy("Generating statutory draft…");
    try {
      const continued = await apiFetch<ContinuedYearEnd>(
        `/trial-balances/${tbId}/statutory-year-end`,
        {
          method: "POST",
          getToken,
          body: JSON.stringify({
            pack_id: selected.packId,
            pack_version: selected.packVersion,
          }),
        },
      );
      setYearEndId(continued.year_end_id);
      setCarried(continued.lines);
      router.push(`/year-ends/${continued.year_end_id}/draft`);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 403) {
        setError(SIGNOFF);
      } else {
        setError(messageFrom(caught));
      }
    } finally {
      setBusy(null);
    }
  }

  async function markFirstPeriod(): Promise<void> {
    if (!yearEndId) {
      return;
    }
    setError(null);
    setBusy("Opening the first-period gate…");
    try {
      await apiFetch(`/year-ends/${yearEndId}/first-financial-period`, {
        method: "POST",
        getToken,
      });
      await loadPack(yearEndId);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  async function downloadPdf(): Promise<void> {
    if (!yearEndId) {
      return;
    }
    setError(null);
    setBusy("Preparing PDF…");
    try {
      const token = await getToken();
      const response = await fetch(
        `${getApiBaseUrl()}/year-ends/${yearEndId}/adopted-trial-balance/statements.pdf`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} },
      );
      if (!response.ok) {
        let detail = `API ${response.status}`;
        try {
          const body = (await response.json()) as { detail?: unknown };
          if (typeof body.detail === "string") {
            detail = body.detail;
          }
        } catch {
          detail = `API ${response.status}`;
        }
        throw new ApiError(detail, response.status, null);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "statutory-statements-draft.pdf";
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  if (!isSignedIn) {
    return <p className="text-sm text-ink-secondary">Sign in to continue.</p>;
  }
  if (meQuery.isLoading) {
    return <p className="text-sm text-soft">Loading statutory accounts…</p>;
  }
  if (meQuery.error) {
    return (
      <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
        {messageFrom(meQuery.error)}
      </p>
    );
  }

  return (
    <div className="space-y-4" data-testid="statutory-continuation">
      <div>
        <h2 className="font-display text-heading-md text-ink">
          Continue to statutory accounts
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-secondary">
          Draft only. This uses the trial balance and confirmed mappings
          already on this page. Period ending{" "}
          <span className="font-medium text-ink">{formatDate(periodEnd)}</span>
          . Nothing here uploads a new file or asks you to map those accounts
          again.
        </p>
      </div>

      {error ? (
        <p
          className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
          data-testid="statutory-error"
        >
          {error}
        </p>
      ) : null}
      {busy ? <p className="text-sm text-soft">{busy}</p> : null}

      {forbidden ? (
        <p className="text-sm text-ink-secondary" data-testid="statutory-signoff">
          {SIGNOFF}
        </p>
      ) : (
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-[16rem] flex-col gap-1.5 text-sm">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
              Reporting framework
            </span>
            <select
              id="statutory-framework"
              data-testid="statutory-framework"
              className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink shadow-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              value={framework}
              disabled={busy !== null}
              onChange={(event) => setFramework(event.target.value)}
            >
              {FRAMEWORKS.map((item) => (
                <option
                  key={frameworkKey(item.packId, item.packVersion)}
                  value={frameworkKey(item.packId, item.packVersion)}
                >
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            data-testid="statutory-generate"
            disabled={busy !== null}
            onClick={() => void generateDraft()}
            className="rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover disabled:opacity-50"
          >
            {busy ? "Working…" : "Generate statutory draft"}
          </button>
        </div>
      )}

      {existingYearEnd.data?.year_end_id ? (
        <p className="text-sm text-ink-secondary">
          <Link
            href={`/year-ends/${existingYearEnd.data.year_end_id}/draft`}
            className="font-medium text-accent underline-offset-2 hover:underline"
            data-testid="statutory-open-workspace"
          >
            Open the statutory workspace
          </Link>{" "}
          for this period. You can leave it and come back to the same address.
        </p>
      ) : null}

      {carried.length > 0 ? (
        <div className="overflow-x-auto rounded-md border border-line bg-surface-elevated">
          <table className="min-w-full text-left text-sm" data-testid="statutory-carried">
            <thead className="border-b border-line bg-accent-muted/50 text-xs uppercase tracking-[0.12em] text-soft">
              <tr>
                <th className="px-4 py-3 font-semibold">Code</th>
                <th className="px-4 py-3 font-semibold">Account</th>
                <th className="px-4 py-3 font-semibold">Confirmed line</th>
                <th className="px-4 py-3 font-semibold">Statutory line</th>
              </tr>
            </thead>
            <tbody>
              {carried.map((line) => (
                <tr key={line.nominal_code} className="border-b border-line/70">
                  <td className="px-4 py-2.5">{line.nominal_code}</td>
                  <td className="px-4 py-2.5">{line.account_name}</td>
                  <td className="px-4 py-2.5">{line.product1_line}</td>
                  <td className="px-4 py-2.5">{line.canonical_line}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {priorYearBlocked && yearEndId ? (
        <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          <p>
            Prior-year comparatives are still required before this draft can
            show figures.
          </p>
          <button
            type="button"
            data-testid="statutory-first-period"
            disabled={busy !== null}
            onClick={() => void markFirstPeriod()}
            className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
          >
            This is the first financial period
          </button>
        </div>
      ) : null}

      {pack ? (
        <section className="space-y-4" data-testid="statutory-pack">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-amber-800">
              {pack.watermark} statutory pack
            </h3>
            <button
              type="button"
              data-testid="statutory-download"
              disabled={busy !== null || !pack.renderable}
              onClick={() => void downloadPdf()}
              className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
            >
              Download draft PDF
            </button>
          </div>
          <p className="text-sm text-ink-secondary">
            Net assets {money(pack.net_assets, currencyCode)}. Profit{" "}
            {money(pack.profit, currencyCode)}.
            {pack.renderable ? " Renderable." : " Not renderable."}
          </p>
          {pack.build_error ? (
            <p className="text-sm text-red-800">{pack.build_error}</p>
          ) : null}
          {pack.checks.filter((check) => !check.passed).length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-sm text-ink-secondary">
              {pack.checks
                .filter((check) => !check.passed)
                .map((check) => (
                  <li key={check.code}>
                    {check.severity} {check.code}: {check.message}
                  </li>
                ))}
            </ul>
          ) : null}
          <PackTable title="Income" rows={pack.income} currency={currencyCode} />
          <PackTable
            title="Financial position"
            rows={pack.sofp}
            currency={currencyCode}
          />
        </section>
      ) : null}
    </div>
  );
}

function PackTable({
  title,
  rows,
  currency,
}: {
  title: string;
  rows: StatementRow[];
  currency: string;
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
            <th className="px-4 py-3 text-right font-semibold">Current</th>
            <th className="px-4 py-3 text-right font-semibold">Prior</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-b border-line/70">
              <td className="px-4 py-2.5">{row.label}</td>
              <td className="px-4 py-2.5 text-right tabular-nums">
                {money(row.current, currency)}
              </td>
              <td className="px-4 py-2.5 text-right tabular-nums">
                {money(row.prior, currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
