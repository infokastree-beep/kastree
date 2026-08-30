"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState, type DragEvent } from "react";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import {
  ACCEPTED_UPLOAD_EXTENSIONS,
  MAX_UPLOAD_BYTES,
} from "@/lib/constants";
import { estimateCsvRowCount, formatBytes } from "@/lib/utils";
import type { ClientListResponse, UploadAcceptedResponse } from "@/types";

function isAcceptedFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  return ACCEPTED_UPLOAD_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export function UploadForm() {
  const router = useRouter();
  const { getToken } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [rowCount, setRowCount] = useState<number | null>(null);
  const [periodEnd, setPeriodEnd] = useState(() => {
    const d = new Date();
    d.setDate(0); // last day of previous month
    return d.toISOString().slice(0, 10);
  });
  const [currency, setCurrency] = useState("GBP");
  const [clientId, setClientId] = useState<string>("");
  const [newClientName, setNewClientName] = useState("Demo Client");
  const [dragOver, setDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const clientsQuery = useQuery({
    queryKey: ["clients"],
    queryFn: () =>
      apiFetch<ClientListResponse>("/clients?limit=50", { getToken }),
  });

  const ensureClient = useCallback(async (): Promise<string> => {
    if (clientId) return clientId;
    const items = clientsQuery.data?.items ?? [];
    if (items.length > 0) {
      setClientId(items[0].id);
      return items[0].id;
    }
    const created = await apiFetch<{ id: string }>("/clients", {
      method: "POST",
      getToken,
      body: JSON.stringify({
        name: newClientName.trim() || "Demo Client",
        functional_currency: currency,
      }),
    });
    setClientId(created.id);
    return created.id;
  }, [clientId, clientsQuery.data?.items, currency, getToken, newClientName]);

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a .xlsx or .csv file first");
      const resolvedClientId = await ensureClient();
      const form = new FormData();
      form.append("file", file);
      form.append("client_id", resolvedClientId);
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

  const clientOptions = useMemo(
    () => clientsQuery.data?.items ?? [],
    [clientsQuery.data?.items],
  );

  const errorMessage =
    localError ||
    (uploadMutation.error instanceof Error
      ? uploadMutation.error.message
      : null) ||
    (clientsQuery.error instanceof Error ? clientsQuery.error.message : null);

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
          <span className="mb-1 block text-stone-600">Client</span>
          {clientOptions.length > 0 ? (
            <select
              className="w-full rounded border border-stone-300 bg-white px-3 py-2"
              value={clientId || clientOptions[0]?.id || ""}
              onChange={(e) => setClientId(e.target.value)}
            >
              {clientOptions.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="w-full rounded border border-stone-300 px-3 py-2"
              value={newClientName}
              onChange={(e) => setNewClientName(e.target.value)}
              placeholder="New client name"
            />
          )}
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
            <option value="GBP">GBP</option>
            <option value="EUR">EUR</option>
            <option value="USD">USD</option>
          </select>
        </label>
      </div>

      {errorMessage ? (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {errorMessage}
        </p>
      ) : null}

      <button
        type="button"
        disabled={!file || uploadMutation.isPending}
        onClick={() => uploadMutation.mutate()}
        className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {uploadMutation.isPending ? "Uploading…" : "Upload and Parse"}
      </button>
    </div>
  );
}
