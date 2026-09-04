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
import { estimateCsvRowCount, formatBytes } from "@/lib/utils";
import type {
  ClientListResponse,
  CompanyListResponse,
  ICompany,
  PriorPeriodPreview,
  UploadAcceptedResponse,
} from "@/types";

const NEW_CLIENT_VALUE = "__new_client__";
const NEW_COMPANY_VALUE = "__new_company__";

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
  const [companyId, setCompanyId] = useState(initialCompanyId);
  const [showAddCompany, setShowAddCompany] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

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

  // Drop company selection when it no longer exists under the chosen client group.
  useEffect(() => {
    if (!clientId) {
      setCompanyId("");
      return;
    }
    if (companyId && !companyOptions.some((company) => company.id === companyId)) {
      setCompanyId("");
      setCurrency("GBP");
    }
  }, [clientId, companyId, companyOptions]);

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

      {priorPreviewQuery.data?.prior_period_end ? (
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
