"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { CompanyEntityForm } from "@/components/clients/CompanyEntityForm";
import type { CompanyEntityFormValues } from "@/lib/company-form";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch, existingTbIdFromConflict, existingTbStatusFromConflict } from "@/lib/api";
import { createCompanyEntity } from "@/lib/companies";
import {
  ACCEPTED_UPLOAD_EXTENSIONS,
  FUNCTIONAL_CURRENCIES,
  MAX_UPLOAD_BYTES,
} from "@/lib/constants";
import {
  filterPriorTbOptions,
  readPreferredPriorTbId,
  writePreferredPriorTbId,
} from "@/lib/prior-period";
import { estimateCsvRowCount, formatBytes, formatDate } from "@/lib/utils";
import type {
  ClientListResponse,
  CompanyListResponse,
  ICompany,
  PriorPeriodPreview,
  TrialBalanceListResponse,
  UploadAcceptedResponse,
} from "@/types";

const NEW_CLIENT_VALUE = "__new_client__";
const NEW_COMPANY_VALUE = "__new_company__";
/** Sentinel: follow auto-detected prior (most recent period before period end). */
const PRIOR_AUTO_VALUE = "__auto__";

function isAcceptedFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  return ACCEPTED_UPLOAD_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function currencyForCompany(company: ICompany | undefined): string {
  return company?.functional_currency ?? "GBP";
}

/** Format YYYY-MM-DD for the prior-period indicator (readable, locale-stable). */
function formatPeriodEndLabel(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!match) return isoDate;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

type UploadFormProps = {
  initialCompanyId?: string;
};

export function UploadForm({ initialCompanyId = "" }: UploadFormProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { getToken } = useAuth();
  const deepLinkInitialized = useRef(false);

  const [file, setFile] = useState<File | null>(null);
  const [rowCount, setRowCount] = useState<number | null>(null);
  const [periodEnd, setPeriodEnd] = useState(() => {
    const d = new Date();
    d.setDate(0);
    return d.toISOString().slice(0, 10);
  });
  const [currency, setCurrency] = useState("GBP");
  const [clientId, setClientId] = useState("");
  // Do not seed companyId from the deep-link prop alone — clientId is still empty on
  // the first paint, and the !clientId effect would immediately clear it. Both are
  // applied together once initialCompanyQuery resolves.
  const [companyId, setCompanyId] = useState("");
  const [showAddCompany, setShowAddCompany] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  /** Manual prior override; empty string means follow auto until the user picks. */
  const [priorOverrideTbId, setPriorOverrideTbId] = useState("");

  const clientsQuery = useQuery({
    queryKey: ["clients"],
    queryFn: () =>
      apiFetch<ClientListResponse>("/clients?limit=100", { getToken }),
  });

  const clientOptions = useMemo(
    () => clientsQuery.data?.items ?? [],
    [clientsQuery.data?.items],
  );

  const companiesQueries = useQueries({
    queries: clientOptions.map((client) => ({
      queryKey: ["companies", client.id],
      queryFn: () =>
        apiFetch<CompanyListResponse>(`/clients/${client.id}/companies`, {
          getToken,
        }),
      enabled: clientsQuery.isSuccess,
    })),
  });

  const companiesByClientId = useMemo(() => {
    const map = new Map<string, CompanyListResponse["items"]>();
    clientOptions.forEach((client, index) => {
      map.set(client.id, companiesQueries[index]?.data?.items ?? []);
    });
    return map;
  }, [clientOptions, companiesQueries]);

  const companyOptions = useMemo(
    () => companiesByClientId.get(clientId) ?? [],
    [companiesByClientId, clientId],
  );

  const companiesQueryIndex = clientOptions.findIndex((client) => client.id === clientId);
  const currentCompaniesQuery =
    companiesQueryIndex >= 0 ? companiesQueries[companiesQueryIndex] : undefined;
  const companiesLoading = Boolean(clientId) && (currentCompaniesQuery?.isLoading ?? true);

  const initialCompanyQuery = useQuery({
    queryKey: ["company", initialCompanyId],
    queryFn: () =>
      apiFetch<ICompany>(`/companies/${initialCompanyId}`, { getToken }),
    enabled: Boolean(initialCompanyId),
  });

  const priorPreviewQuery = useQuery({
    queryKey: ["prior-period-preview", companyId, periodEnd],
    queryFn: () =>
      apiFetch<PriorPeriodPreview>(
        `/trial-balances/prior-period-preview?company_id=${encodeURIComponent(companyId)}&period_end=${encodeURIComponent(periodEnd)}`,
        { getToken },
      ),
    enabled: Boolean(companyId && periodEnd),
  });

  const priorListQuery = useQuery({
    queryKey: ["trial-balances", "upload-priors", companyId],
    queryFn: () =>
      apiFetch<TrialBalanceListResponse>(
        `/trial-balances?company_id=${encodeURIComponent(companyId)}&limit=100`,
        { getToken },
      ),
    enabled: Boolean(companyId),
  });

  const priorOptions = useMemo(
    () => filterPriorTbOptions(priorListQuery.data?.items ?? [], periodEnd),
    [priorListQuery.data?.items, periodEnd],
  );

  // Restore upload preference when company or period changes.
  useEffect(() => {
    if (!companyId || !periodEnd) {
      setPriorOverrideTbId("");
      return;
    }
    const preferred = readPreferredPriorTbId(companyId, periodEnd);
    if (preferred && priorOptions.some((tb) => tb.id === preferred)) {
      setPriorOverrideTbId(preferred);
      return;
    }
    setPriorOverrideTbId("");
  }, [companyId, periodEnd, priorOptions]);

  const effectivePriorTbId =
    priorOverrideTbId ||
    priorPreviewQuery.data?.prior_tb_id ||
    priorOptions[0]?.id ||
    null;

  const effectivePriorPeriodEnd =
    priorOptions.find((tb) => tb.id === effectivePriorTbId)?.period_end ??
    priorPreviewQuery.data?.prior_period_end ??
    null;

  const isManualPrior =
    Boolean(priorOverrideTbId) &&
    priorOverrideTbId !== (priorPreviewQuery.data?.prior_tb_id ?? "");

  // Deep link: apply once when ?company= resolves — never re-apply on refetch (that
  // would undo manual company/currency changes after the user switches selection).
  useEffect(() => {
    if (!initialCompanyId || !initialCompanyQuery.data || deepLinkInitialized.current) {
      return;
    }
    deepLinkInitialized.current = true;
    setClientId(initialCompanyQuery.data.client_id);
    setCompanyId(initialCompanyQuery.data.id);
    setCurrency(initialCompanyQuery.data.functional_currency);
  }, [initialCompanyId, initialCompanyQuery.data]);

  // Re-assert deep-linked company once that client's options have loaded. A controlled
  // <select> can drop a value that was set before its <option> existed; without this,
  // ?company= leaves client+currency set but company blank. Only repairs an empty
  // companyId — never overrides a deliberate manual company change.
  useEffect(() => {
    if (!deepLinkInitialized.current || !initialCompanyQuery.data) {
      return;
    }
    if (companiesLoading || companyOptions.length === 0 || companyId) {
      return;
    }
    const target = initialCompanyQuery.data;
    if (clientId !== target.client_id) {
      return;
    }
    if (companyOptions.some((company) => company.id === target.id)) {
      setCompanyId(target.id);
      setCurrency(target.functional_currency);
    }
  }, [
    clientId,
    companyId,
    companyOptions,
    companiesLoading,
    initialCompanyQuery.data,
  ]);

  // Drop company selection when it no longer exists under the chosen client group.
  // Wait until companies have loaded with a non-empty options list — an empty list
  // during/after fetch must not wipe a deep-linked companyId before options arrive.
  useEffect(() => {
    if (!clientId) {
      // Keep company unset while a deep-linked company fetch is still in flight;
      // clearing here races the deep-link effect that sets client + company together.
      if (!initialCompanyId || deepLinkInitialized.current) {
        setCompanyId("");
      }
      return;
    }
    if (companiesLoading || companyOptions.length === 0) {
      return;
    }
    if (companyId && !companyOptions.some((company) => company.id === companyId)) {
      setCompanyId("");
      setCurrency("GBP");
    }
  }, [
    clientId,
    companyId,
    companyOptions,
    companiesLoading,
    initialCompanyId,
  ]);

  const addCompanyMutation = useMutation({
    mutationFn: (values: CompanyEntityFormValues) =>
      createCompanyEntity(clientId, values, getToken),
    onSuccess: (company) => {
      setShowAddCompany(false);
      void queryClient.invalidateQueries({ queryKey: ["companies", clientId] });
      void queryClient.invalidateQueries({ queryKey: ["clients"] });
      setCompanyId(company.id);
      setCurrency(company.functional_currency);
    },
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a .xlsx or .csv file first");
      if (!companyId) throw new Error("Select a company before uploading");
      const form = new FormData();
      form.append("file", file);
      form.append("company_id", companyId);
      form.append("period_end", periodEnd);
      form.append("currency", currency);
      return apiFetch<UploadAcceptedResponse>("/trial-balances/upload", {
        method: "POST",
        getToken,
        body: form,
      });
    },
    onSuccess: (data) => {
      // Persist prior choice so Variance tab boots to the same comparison.
      if (companyId && periodEnd && effectivePriorTbId) {
        writePreferredPriorTbId(companyId, periodEnd, effectivePriorTbId);
      }
      router.push(`/mapping/${data.tb_id}`);
    },
  });

  const onPickFile = useCallback(async (next: File | null) => {
    setLocalError(null);
    setRowCount(null);
    if (!next) {
      setFile(null);
      return;
    }
    if (!isAcceptedFile(next)) {
      setLocalError("Only .xlsx and .csv files are accepted.");
      setFile(null);
      return;
    }
    if (next.size > MAX_UPLOAD_BYTES) {
      setLocalError("File exceeds the 50MB limit.");
      setFile(null);
      return;
    }
    setFile(next);
    const estimated = await estimateCsvRowCount(next);
    setRowCount(estimated);
  }, []);

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragOver(false);
      const dropped = event.dataTransfer.files?.[0] ?? null;
      void onPickFile(dropped);
    },
    [onPickFile],
  );

  const onClientChange = useCallback(
    (value: string) => {
      if (value === NEW_CLIENT_VALUE) {
        router.push("/clients/new");
        return;
      }
      setClientId(value);
      setCompanyId("");
      setShowAddCompany(false);
      setCurrency("GBP");
    },
    [router],
  );

  const onCompanyChange = useCallback(
    (value: string) => {
      if (value === NEW_COMPANY_VALUE) {
        setShowAddCompany(true);
        setCompanyId("");
        return;
      }
      setShowAddCompany(false);
      setCompanyId(value);
      const selected = companyOptions.find((company) => company.id === value);
      setCurrency(currencyForCompany(selected));
    },
    [companyOptions],
  );

  const onPriorOverrideChange = useCallback(
    (value: string) => {
      if (!companyId || !periodEnd) return;
      if (value === PRIOR_AUTO_VALUE) {
        setPriorOverrideTbId("");
        writePreferredPriorTbId(companyId, periodEnd, null);
        return;
      }
      setPriorOverrideTbId(value);
      writePreferredPriorTbId(companyId, periodEnd, value);
    },
    [companyId, periodEnd],
  );

  const addCompanyError =
    addCompanyMutation.error instanceof Error ? addCompanyMutation.error.message : null;

  const conflictTbId = existingTbIdFromConflict(uploadMutation.error);
  const conflictTbStatus = existingTbStatusFromConflict(uploadMutation.error);
  const conflictHref =
    conflictTbId == null
      ? null
      : conflictTbStatus === "complete" ||
          conflictTbStatus === "validating" ||
          conflictTbStatus === "generating" ||
          conflictTbStatus === "analysing"
        ? `/dashboard/${conflictTbId}`
        : `/mapping/${conflictTbId}`;

  const errorMessage =
    localError ||
    (uploadMutation.error instanceof Error
      ? uploadMutation.error.message
      : null) ||
    (clientsQuery.error instanceof Error ? clientsQuery.error.message : null) ||
    (initialCompanyQuery.error instanceof Error
      ? initialCompanyQuery.error.message
      : null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Upload trial balance</h1>
        <p className="mt-1 text-sm text-stone-600">
          Drop an Excel or CSV file, then parse and map accounts.
        </p>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={`rounded border-2 border-dashed px-6 py-12 text-center ${
          dragOver ? "border-stone-900 bg-stone-100" : "border-stone-300 bg-white"
        }`}
      >
        <p className="text-sm font-medium">Drag and drop .xlsx or .csv</p>
        <p className="mt-1 text-xs text-stone-500">or</p>
        <label className="mt-3 inline-block cursor-pointer rounded bg-stone-900 px-3 py-2 text-sm font-medium text-white">
          Choose file
          <input
            type="file"
            accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
            className="hidden"
            onChange={(e) => void onPickFile(e.target.files?.[0] ?? null)}
          />
        </label>
      </div>

      {file ? (
        <div className="rounded border border-stone-200 bg-white p-4 text-sm">
          <p className="font-medium">{file.name}</p>
          <dl className="mt-2 grid grid-cols-2 gap-2 text-stone-600 sm:grid-cols-3">
            <div>
              <dt className="text-xs uppercase tracking-wide text-stone-400">Size</dt>
              <dd>{formatBytes(file.size)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-stone-400">
                Row count
              </dt>
              <dd>
                {rowCount !== null
                  ? rowCount
                  : "Available after parse (xlsx)"}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-stone-400">Type</dt>
              <dd>{file.name.toLowerCase().endsWith(".csv") ? "CSV" : "Excel"}</dd>
            </div>
          </dl>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block text-stone-600">Client group</span>
          <select
            className="w-full rounded border border-stone-300 bg-white px-3 py-2"
            value={clientId}
            onChange={(e) => onClientChange(e.target.value)}
            disabled={clientsQuery.isLoading}
          >
            <option value="">
              {clientsQuery.isLoading ? "Loading clients…" : "Select a client group"}
            </option>
            {clientOptions.map((client) => (
              <option key={client.id} value={client.id}>
                {client.name}
              </option>
            ))}
            <option value={NEW_CLIENT_VALUE}>+ New client</option>
          </select>
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-stone-600">Company</span>
          <select
            className="w-full rounded border border-stone-300 bg-white px-3 py-2"
            value={showAddCompany ? NEW_COMPANY_VALUE : companyId}
            onChange={(e) => onCompanyChange(e.target.value)}
            disabled={!clientId || companiesLoading}
          >
            <option value="">
              {!clientId
                ? "Select a client group first"
                : companiesLoading
                  ? "Loading companies…"
                  : companyOptions.length === 0
                    ? "No companies yet"
                    : "Select a company"}
            </option>
            {companyOptions.map((company) => (
              <option key={company.id} value={company.id}>
                {company.name} ({company.functional_currency})
              </option>
            ))}
            {clientId && !companiesLoading ? (
              <option value={NEW_COMPANY_VALUE}>+ New company</option>
            ) : null}
          </select>
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-stone-600">Period end</span>
          <input
            type="date"
            className="w-full rounded border border-stone-300 px-3 py-2"
            value={periodEnd}
            onChange={(e) => setPeriodEnd(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-stone-600">Currency</span>
          <select
            className="w-full rounded border border-stone-300 bg-white px-3 py-2"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            {FUNCTIONAL_CURRENCIES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
      </div>

      {companyId && periodEnd && priorOptions.length > 0 ? (
        <div
          className="space-y-3 rounded border border-teal-200 bg-teal-50/80 px-3 py-3"
          data-testid="prior-period-indicator"
        >
          <p className="text-sm text-teal-950">
            {effectivePriorPeriodEnd ? (
              <>
                This will be compared against{" "}
                <span className="font-medium">
                  {formatPeriodEndLabel(effectivePriorPeriodEnd)}
                </span>
                {priorPreviewQuery.data?.company_name ? (
                  <>
                    {" "}
                    for{" "}
                    <span className="font-medium">
                      {priorPreviewQuery.data.company_name}
                    </span>
                  </>
                ) : null}
                {isManualPrior ? " (manual override)." : " (auto-detected)."}{" "}
                Variance uses this after statements are generated.
              </>
            ) : (
              "Select a prior period to compare against once statements are generated."
            )}
          </p>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-teal-900">
              Compare against
            </span>
            <select
              data-testid="upload-prior-select"
              className="w-full max-w-md rounded border border-teal-300 bg-white px-3 py-2 text-teal-950"
              value={priorOverrideTbId || PRIOR_AUTO_VALUE}
              onChange={(e) => onPriorOverrideChange(e.target.value)}
              disabled={priorListQuery.isLoading}
            >
              <option value={PRIOR_AUTO_VALUE}>
                Auto
                {priorPreviewQuery.data?.prior_period_end
                  ? ` — ${formatPeriodEndLabel(priorPreviewQuery.data.prior_period_end)}`
                  : priorOptions[0]
                    ? ` — ${formatDate(priorOptions[0].period_end)}`
                    : ""}
              </option>
              {priorOptions.map((tb) => (
                <option key={tb.id} value={tb.id}>
                  {formatPeriodEndLabel(tb.period_end)}
                  {tb.id === priorPreviewQuery.data?.prior_tb_id ? " (auto)" : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : priorPreviewQuery.data?.prior_period_end ? (
        <p
          className="rounded border border-teal-200 bg-teal-50/80 px-3 py-2 text-sm text-teal-950"
          data-testid="prior-period-indicator"
        >
          This will be compared against your{" "}
          <span className="font-medium">
            {formatPeriodEndLabel(priorPreviewQuery.data.prior_period_end)}
          </span>{" "}
          upload for{" "}
          <span className="font-medium">{priorPreviewQuery.data.company_name}</span>{" "}
          once statements are generated.
        </p>
      ) : null}

      {showAddCompany && clientId ? (
        <div className="rounded border border-stone-200 bg-white p-4">
          <CompanyEntityForm
            intro={
              <p className="text-sm text-stone-600">
                Add a company to this client group. It will be selected automatically
                when created.
              </p>
            }
            submitLabel="Add company"
            isPending={addCompanyMutation.isPending}
            errorMessage={addCompanyError}
            onSubmit={(values) => addCompanyMutation.mutate(values)}
            onCancel={() => {
              setShowAddCompany(false);
              addCompanyMutation.reset();
            }}
          />
        </div>
      ) : null}

      {clientOptions.length === 0 && !clientsQuery.isLoading ? (
        <p className="text-xs text-stone-500">
          No clients yet. Choose{" "}
          <Link href="/clients/new" className="underline">
            + New client
          </Link>
          .
        </p>
      ) : null}

      {errorMessage ? (
        <div className="space-y-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <p>{errorMessage}</p>
          {conflictHref ? (
            <p>
              <Link href={conflictHref} className="font-medium underline">
                Open the existing trial balance
              </Link>
              {conflictTbStatus ? ` (status: ${conflictTbStatus})` : null}
            </p>
          ) : null}
        </div>
      ) : null}

      <button
        type="button"
        disabled={!file || !companyId || uploadMutation.isPending}
        onClick={() => uploadMutation.mutate()}
        className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {uploadMutation.isPending ? "Uploading…" : "Upload and Parse"}
      </button>
    </div>
  );
}
