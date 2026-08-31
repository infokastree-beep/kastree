"use client";

import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type DragEvent } from "react";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
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
  UploadAcceptedResponse,
} from "@/types";

const NEW_CLIENT_VALUE = "__new_client__";

function isAcceptedFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  return ACCEPTED_UPLOAD_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

type UploadFormProps = {
  initialCompanyId?: string;
};

export function UploadForm({ initialCompanyId = "" }: UploadFormProps) {
  const router = useRouter();
  const { getToken } = useAuth();
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

  const initialCompanyQuery = useQuery({
    queryKey: ["company", initialCompanyId],
    queryFn: () =>
      apiFetch<ICompany>(`/companies/${initialCompanyId}`, { getToken }),
    enabled: Boolean(initialCompanyId),
  });

  useEffect(() => {
    if (initialCompanyQuery.data) {
      setClientId(initialCompanyQuery.data.client_id);
      setCompanyId(initialCompanyQuery.data.id);
      setCurrency(initialCompanyQuery.data.functional_currency);
    }
  }, [initialCompanyQuery.data]);

  useEffect(() => {
    const selected = companyOptions.find((company) => company.id === companyId);
    if (selected) {
      setCurrency(selected.functional_currency);
    }
  }, [companyId, companyOptions]);

  useEffect(() => {
    if (!clientId) {
      setCompanyId("");
      return;
    }
    if (companyId && !companyOptions.some((company) => company.id === companyId)) {
      setCompanyId("");
    }
  }, [clientId, companyId, companyOptions]);

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
    },
    [router],
  );

  const companiesLoading = companiesQueries.some((query) => query.isLoading);

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
            value={companyId}
            onChange={(e) => setCompanyId(e.target.value)}
            disabled={!clientId || companiesLoading}
          >
            <option value="">
              {!clientId
                ? "Select a client group first"
                : companiesLoading
                  ? "Loading companies…"
                  : companyOptions.length === 0
                    ? "No companies — create one first"
                    : "Select a company"}
            </option>
            {companyOptions.map((company) => (
              <option key={company.id} value={company.id}>
                {company.name} ({company.functional_currency})
              </option>
            ))}
          </select>
          {clientId && !companiesLoading && companyOptions.length === 0 ? (
            <p className="mt-1 text-xs text-stone-500">
              <Link href={`/clients/${clientId}`} className="underline">
                Add a company
              </Link>{" "}
              to this client group before uploading.
            </p>
          ) : null}
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
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {errorMessage}
        </p>
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
