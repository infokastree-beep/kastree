"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { downloadDraftPdf, pdfBlockReason } from "@/lib/draft-pdf";
import { formatCurrency } from "@/lib/currency";
import { statutoryWorkspaceOpen, type StatutoryUser } from "@/lib/statutory-gate";
import { StatutoryOptIn } from "@/components/statutory/StatutoryOptIn";
import { confidenceBadgeClass, formatConfidence } from "@/lib/utils";
import type { ClientListResponse, CompanyListResponse, ICompany } from "@/types";

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

type AdoptableTrialBalance = {
  id: string;
  period_end: string;
  currency: string | null;
  account_count: number;
};

type CarriedMapping = {
  nominal_code: string;
  account_name: string;
  product1_line: string;
  canonical_line: string;
};

type TbVersion = {
  id: string;
  status: string;
  error_message: string | null;
  version_number: number;
};

type TbLine = {
  line_no: number;
  nominal_code: string;
  account_name: string;
  debit: string;
  credit: string;
  suggested_canonical_line: string | null;
  confidence: string | null;
  method: string | null;
};

function confidenceNumber(value: string | null): number | null {
  if (value === null || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

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

export function StatutoryWorkbench() {
  const { getToken, isSignedIn } = useAuth();
  const meQuery = useQuery({
    queryKey: ["users", "me"],
    queryFn: () => apiFetch<StatutoryUser>("/users/me", { getToken }),
    enabled: isSignedIn,
  });

  const clientsQuery = useQuery({
    queryKey: ["clients"],
    queryFn: () =>
      apiFetch<ClientListResponse>("/clients?limit=100", { getToken }),
    enabled: statutoryWorkspaceOpen(meQuery.data),
  });

  const [clientId, setClientId] = useState("");
  const companiesQuery = useQuery({
    queryKey: ["companies", clientId],
    queryFn: () =>
      apiFetch<CompanyListResponse>(`/clients/${clientId}/companies`, {
        getToken,
      }),
    enabled: clientId.length > 0,
  });

  const [companyId, setCompanyId] = useState("");
  const [periodStart, setPeriodStart] = useState("2026-01-01");
  const [periodEnd, setPeriodEnd] = useState("2026-12-31");
  const [yearEnd, setYearEnd] = useState<YearEnd | null>(null);
  const [selectedTbId, setSelectedTbId] = useState("");
  const [carried, setCarried] = useState<CarriedMapping[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [version, setVersion] = useState<TbVersion | null>(null);
  const [lines, setLines] = useState<TbLine[]>([]);
  const [catalogue, setCatalogue] = useState<string[]>([]);
  const [mappings, setMappings] = useState<Record<string, string>>({});
  const [pack, setPack] = useState<StatementPack | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const adoptableQuery = useQuery({
    queryKey: ["adoptable-trial-balances", yearEnd?.id],
    queryFn: () =>
      apiFetch<{ items: AdoptableTrialBalance[] }>(
        `/year-ends/${yearEnd?.id}/adoptable-trial-balances`,
        { getToken },
      ),
    enabled: yearEnd !== null,
  });

  const company: ICompany | undefined = useMemo(
    () => companiesQuery.data?.items.find((item) => item.id === companyId),
    [companiesQuery.data, companyId],
  );
  const currency = company?.functional_currency ?? "EUR";
  const nominalCodes = useMemo(() => {
    const seen: string[] = [];
    for (const line of lines) {
      if (!seen.includes(line.nominal_code)) {
        seen.push(line.nominal_code);
      }
    }
    return seen;
  }, [lines]);

  if (!isSignedIn) {
    return <p className="text-sm text-stone-600">Sign in to continue.</p>;
  }
  if (meQuery.isLoading) {
    return <p className="text-sm text-stone-600">Loading…</p>;
  }
  if (meQuery.error) {
    return (
      <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
        {messageFrom(meQuery.error)}
      </p>
    );
  }
  if (!statutoryWorkspaceOpen(meQuery.data)) {
    return (
      <StatutoryOptIn
        email={meQuery.data?.email}
        role={meQuery.data?.role}
      />
    );
  }

  async function createYearEnd() {
    setError(null);
    setBusy("Creating year end…");
    try {
      const created = await apiFetch<YearEnd>("/year-ends", {
        method: "POST",
        getToken,
        body: JSON.stringify({
          company_id: companyId,
          period_start: periodStart,
          period_end: periodEnd,
        }),
      });
      setYearEnd(created);
      setSelectedTbId("");
      setCarried([]);
      setVersion(null);
      setLines([]);
      setPack(null);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  async function markFirstPeriod() {
    if (!yearEnd) {
      return;
    }
    setError(null);
    setBusy("Opening the first-period gate…");
    try {
      const updated = await apiFetch<YearEnd>(
        `/year-ends/${yearEnd.id}/first-financial-period`,
        { method: "POST", getToken },
      );
      setYearEnd(updated);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  async function adoptConfirmedTrialBalance() {
    if (!yearEnd || selectedTbId.length === 0) {
      return;
    }
    setError(null);
    setBusy("Using the confirmed trial balance…");
    try {
      const adopted = await apiFetch<{
        trial_balance_id: string;
        lines: CarriedMapping[];
      }>(`/year-ends/${yearEnd.id}/adopt-trial-balance`, {
        method: "POST",
        getToken,
        body: JSON.stringify({ trial_balance_id: selectedTbId }),
      });
      setCarried(adopted.lines);
      setVersion(null);
      setLines([]);
      setMappings({});
      const statements = await apiFetch<StatementPack>(
        `/year-ends/${yearEnd.id}/adopted-trial-balance/statements`,
        { getToken },
      );
      setPack(statements);
      setYearEnd({ ...yearEnd, adopted_trial_balance_id: adopted.trial_balance_id });
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  async function uploadAndImport() {
    if (!yearEnd || !file) {
      return;
    }
    setError(null);
    setBusy("Uploading trial balance…");
    try {
      const body = new FormData();
      body.set("company_id", yearEnd.company_id);
      body.set("file", file);
      const uploaded = await apiFetch<{ id: string }>("/source-documents", {
        method: "POST",
        getToken,
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body,
      });
      setBusy("Importing trial balance…");
      const queued = await apiFetch<TbVersion>(
        `/year-ends/${yearEnd.id}/trial-balance-versions`,
        {
          method: "POST",
          getToken,
          headers: { "Idempotency-Key": crypto.randomUUID() },
          body: JSON.stringify({ source_document_id: uploaded.id }),
        },
      );
      let current = queued;
      for (let attempt = 0; attempt < 30 && current.status === "pending"; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        current = await apiFetch<TbVersion>(
          `/year-ends/${yearEnd.id}/trial-balance-versions/${queued.id}`,
          { getToken },
        );
      }
      setVersion(current);
      if (current.status !== "ready") {
        setError(current.error_message ?? "Trial balance import did not finish.");
        return;
      }
      const [loadedLines, loadedCatalogue] = await Promise.all([
        apiFetch<{ lines: TbLine[] }>(
          `/year-ends/${yearEnd.id}/trial-balance-versions/${current.id}/lines`,
          { getToken },
        ),
        apiFetch<{ lines: string[] }>("/year-ends/canonical-lines", { getToken }),
      ]);
      setLines(loadedLines.lines);
      setCatalogue(loadedCatalogue.lines);
      const suggested: Record<string, string> = {};
      for (const line of loadedLines.lines) {
        if (line.suggested_canonical_line) {
          suggested[line.nominal_code] = line.suggested_canonical_line;
        }
      }
      setMappings(suggested);
      setPack(null);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  async function confirmMappings() {
    if (!yearEnd || !version) {
      return;
    }
    setError(null);
    setBusy("Confirming mappings…");
    try {
      await apiFetch(
        `/year-ends/${yearEnd.id}/trial-balance-versions/${version.id}/mappings`,
        {
          method: "POST",
          getToken,
          body: JSON.stringify({
            lines: nominalCodes.map((nominal_code) => ({
              nominal_code,
              canonical_line: mappings[nominal_code],
            })),
          }),
        },
      );
      const statements = await apiFetch<StatementPack>(
        `/year-ends/${yearEnd.id}/trial-balance-versions/${version.id}/statements`,
        { getToken },
      );
      setPack(statements);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(null);
    }
  }

  async function downloadPdf() {
    if (!yearEnd) {
      return;
    }
    const pdfPath = version
      ? `/year-ends/${yearEnd.id}/trial-balance-versions/${version.id}/statements.pdf`
      : yearEnd.adopted_trial_balance_id
        ? `/year-ends/${yearEnd.id}/adopted-trial-balance/statements.pdf`
        : null;
    if (!pdfPath) {
      return;
    }
    if (
      pdfBlockReason({
        statementsError: null,
        dashboardError: null,
        renderable: pack?.renderable ?? null,
        checks: pack?.checks ?? [],
      }) !== null
    ) {
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

  const mappingsComplete =
    nominalCodes.length > 0 &&
    nominalCodes.every((code) => (mappings[code] ?? "").length > 0);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Statutory accounts</h1>
        <p className="mt-1 max-w-3xl text-sm text-stone-600">
          Draft only. The Irish FRS 102 Section 1A pack is not signed off for
          filing, and this screen is limited to platform administrators. A
          completed Product 1 trial balance can be selected with its confirmed
          mappings. Figures come from that trial balance. Nothing here
          recalculates them.
        </p>
      </div>

      {error ? (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      ) : null}
      {busy ? <p className="text-sm text-stone-600">{busy}</p> : null}

      <section className="space-y-3 rounded border border-stone-200 bg-white p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Year end
        </h2>
        {clientsQuery.isLoading ? (
          <p className="text-sm text-stone-600">Loading clients…</p>
        ) : (clientsQuery.data?.items.length ?? 0) === 0 ? (
          <p className="text-sm text-stone-600">
            No clients yet.{" "}
            <Link href="/clients/new" className="font-medium underline">
              Create a client
            </Link>{" "}
            and a company first.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="mb-1 block text-stone-600">Client</span>
              <select
                className="w-full rounded border border-stone-300 px-2 py-2"
                value={clientId}
                onChange={(event) => {
                  setClientId(event.target.value);
                  setCompanyId("");
                }}
              >
                <option value="">Select a client</option>
                {clientsQuery.data?.items.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-stone-600">Company</span>
              <select
                className="w-full rounded border border-stone-300 px-2 py-2"
                value={companyId}
                onChange={(event) => setCompanyId(event.target.value)}
              >
                <option value="">Select a company</option>
                {companiesQuery.data?.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-stone-600">Period start</span>
              <input
                type="date"
                className="w-full rounded border border-stone-300 px-2 py-2"
                value={periodStart}
                onChange={(event) => setPeriodStart(event.target.value)}
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-stone-600">Period end</span>
              <input
                type="date"
                className="w-full rounded border border-stone-300 px-2 py-2"
                value={periodEnd}
                onChange={(event) => setPeriodEnd(event.target.value)}
              />
            </label>
          </div>
        )}
        <button
          type="button"
          className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          disabled={busy !== null || companyId.length === 0}
          onClick={() => void createYearEnd()}
        >
          Create year end
        </button>
        {yearEnd ? (
          <p className="text-sm text-stone-700">
            Year end {yearEnd.period_start} to {yearEnd.period_end}. Pack{" "}
            {yearEnd.pack_id} {yearEnd.pack_version}.
            {yearEnd.first_financial_period
              ? " Marked as the first financial period."
              : " Prior-year comparatives are still required."}
          </p>
        ) : null}
        {yearEnd && !yearEnd.first_financial_period ? (
          <button
            type="button"
            className="rounded border border-stone-300 px-4 py-2 text-sm font-medium disabled:opacity-50"
            disabled={busy !== null}
            onClick={() => void markFirstPeriod()}
          >
            This is the first financial period
          </button>
        ) : null}
      </section>

      <section className="space-y-3 rounded border border-stone-200 bg-white p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Confirmed trial balance
        </h2>
        <p className="text-sm text-stone-600">
          Choose a completed Product 1 trial balance for this company and
          period. Its confirmed mappings are carried forward. This does not
          upload a new file or ask you to confirm those mappings again.
        </p>
        {adoptableQuery.isLoading ? (
          <p className="text-sm text-stone-600">Loading trial balances…</p>
        ) : (adoptableQuery.data?.items.length ?? 0) === 0 ? (
          <p className="text-sm text-stone-600">
            No completed, fully confirmed trial balance matches this year end.
          </p>
        ) : (
          <label className="block text-sm">
            <span className="mb-1 block text-stone-600">Trial balance</span>
            <select
              className="w-full rounded border border-stone-300 px-2 py-2"
              value={selectedTbId}
              onChange={(event) => setSelectedTbId(event.target.value)}
            >
              <option value="">Select a trial balance</option>
              {adoptableQuery.data?.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.period_end} · {item.account_count} accounts
                  {item.currency ? ` · ${item.currency}` : ""}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          type="button"
          className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          disabled={busy !== null || !yearEnd || selectedTbId.length === 0}
          onClick={() => void adoptConfirmedTrialBalance()}
        >
          Use confirmed trial balance
        </button>
        {carried.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-stone-200 text-xs uppercase tracking-wide text-stone-500">
                <tr>
                  <th className="px-2 py-2 font-medium">Code</th>
                  <th className="px-2 py-2 font-medium">Account</th>
                  <th className="px-2 py-2 font-medium">Confirmed line</th>
                  <th className="px-2 py-2 font-medium">Statutory line</th>
                </tr>
              </thead>
              <tbody>
                {carried.map((line) => (
                  <tr key={line.nominal_code} className="border-b border-stone-100">
                    <td className="px-2 py-2">{line.nominal_code}</td>
                    <td className="px-2 py-2">{line.account_name}</td>
                    <td className="px-2 py-2">{line.product1_line}</td>
                    <td className="px-2 py-2">{line.canonical_line}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="space-y-3 rounded border border-stone-200 bg-white p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Or upload a new file
        </h2>
        <input
          type="file"
          accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <button
          type="button"
          className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          disabled={busy !== null || !yearEnd || !file}
          onClick={() => void uploadAndImport()}
        >
          Upload and import
        </button>
        {version ? (
          <p className="text-sm text-stone-700">
            Version {version.version_number}: {version.status}
            {version.error_message ? ` — ${version.error_message}` : ""}
          </p>
        ) : null}
      </section>

      {lines.length > 0 ? (
        <section className="space-y-3 rounded border border-stone-200 bg-white p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
            Mappings
          </h2>
          <p className="text-sm text-stone-600">
            Each account is pre-filled from the statutory mapping engine.
            Check the suggestion and its confidence, then confirm.
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-stone-200 text-xs uppercase tracking-wide text-stone-500">
                <tr>
                  <th className="px-2 py-2 font-medium">Code</th>
                  <th className="px-2 py-2 font-medium">Account</th>
                  <th className="px-2 py-2 font-medium">Debit</th>
                  <th className="px-2 py-2 font-medium">Credit</th>
                  <th className="px-2 py-2 font-medium">Canonical line</th>
                  <th className="px-2 py-2 font-medium">Confidence</th>
                  <th className="px-2 py-2 font-medium">Method</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line) => (
                  <tr key={line.line_no} className="border-b border-stone-100">
                    <td className="px-2 py-2">{line.nominal_code}</td>
                    <td className="px-2 py-2">{line.account_name}</td>
                    <td className="px-2 py-2">{money(line.debit, currency)}</td>
                    <td className="px-2 py-2">{money(line.credit, currency)}</td>
                    <td className="px-2 py-2">
                      <select
                        className="w-full min-w-48 rounded border border-stone-300 px-2 py-1"
                        value={
                          mappings[line.nominal_code] ??
                          line.suggested_canonical_line ??
                          ""
                        }
                        onChange={(event) =>
                          setMappings((current) => ({
                            ...current,
                            [line.nominal_code]: event.target.value,
                          }))
                        }
                      >
                        <option value="">Select</option>
                        {catalogue.map((lineName) => (
                          <option key={lineName} value={lineName}>
                            {lineName}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-2 py-2">
                      <span
                        className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${confidenceBadgeClass(confidenceNumber(line.confidence))}`}
                      >
                        {formatConfidence(confidenceNumber(line.confidence))}
                      </span>
                    </td>
                    <td className="px-2 py-2">
                      {line.method ? (
                        <span className="rounded bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-700">
                          {line.method}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            disabled={busy !== null || !mappingsComplete || !yearEnd?.first_financial_period}
            onClick={() => void confirmMappings()}
          >
            Confirm mappings and build draft
          </button>
          {yearEnd && !yearEnd.first_financial_period ? (
            <p className="text-sm text-stone-600">
              Mark the first financial period before building the draft. A
              prior-year comparative entry is not on this screen.
            </p>
          ) : null}
        </section>
      ) : null}

      {pack ? (
        <section className="space-y-4 rounded border border-stone-200 bg-white p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-amber-800">
              {pack.watermark} statutory pack
            </h2>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                data-testid="statutory-download"
                className="rounded border border-stone-300 px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
                disabled={
                  busy !== null ||
                  pdfBlockReason({
                    statementsError: null,
                    dashboardError: null,
                    renderable: pack.renderable,
                    checks: pack.checks,
                  }) !== null
                }
                onClick={() => void downloadPdf()}
              >
                Download draft PDF
              </button>
              {pdfBlockReason({
                statementsError: null,
                dashboardError: null,
                renderable: pack.renderable,
                checks: pack.checks,
              }) !== null ? (
                <p className="text-sm text-stone-600" data-testid="statutory-download-reason">
                  {pdfBlockReason({
                    statementsError: null,
                    dashboardError: null,
                    renderable: pack.renderable,
                    checks: pack.checks,
                  })}
                </p>
              ) : null}
            </div>
          </div>
          <p className="text-sm text-stone-700">
            Net assets {money(pack.net_assets, currency)}. Profit{" "}
            {money(pack.profit, currency)}.
            {pack.renderable ? " Renderable." : " Not renderable."}
          </p>
          {pack.build_error ? (
            <p className="text-sm text-red-800">{pack.build_error}</p>
          ) : null}
          {pack.checks.filter((check) => !check.passed).length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-sm text-stone-700">
              {pack.checks
                .filter((check) => !check.passed)
                .map((check) => (
                  <li key={check.code}>
                    {check.severity} {check.code}: {check.message}
                  </li>
                ))}
            </ul>
          ) : null}
          <StatementTable title="Income" rows={pack.income} currency={currency} />
          <StatementTable
            title="Financial position"
            rows={pack.sofp}
            currency={currency}
          />
        </section>
      ) : null}
    </div>
  );
}

function StatementTable({
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
    <div className="overflow-x-auto">
      <h3 className="mb-2 text-sm font-medium">{title}</h3>
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-stone-200 text-xs uppercase tracking-wide text-stone-500">
          <tr>
            <th className="px-2 py-2 font-medium">Line</th>
            <th className="px-2 py-2 font-medium">Current</th>
            <th className="px-2 py-2 font-medium">Prior</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-b border-stone-100">
              <td className="px-2 py-2">{row.label}</td>
              <td className="px-2 py-2">{money(row.current, currency)}</td>
              <td className="px-2 py-2">{money(row.prior, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
