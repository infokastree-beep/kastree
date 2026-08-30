"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/utils";
import type { IClient, TrialBalanceListResponse } from "@/types";

const TB_PAGE_SIZE = 20;

export function ClientDetail({ clientId }: { clientId: string }) {
  const { getToken } = useAuth();

  const clientQuery = useQuery({
    queryKey: ["client", clientId],
    queryFn: () => apiFetch<IClient>(`/clients/${clientId}`, { getToken }),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 2,
  });

  const trialBalancesQuery = useQuery({
    queryKey: ["trial-balances", clientId],
    queryFn: () =>
      apiFetch<TrialBalanceListResponse>(
        `/trial-balances?client_id=${clientId}&limit=${TB_PAGE_SIZE}`,
        { getToken },
      ),
    enabled: clientQuery.isSuccess,
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 2,
  });

  if (clientQuery.isLoading) {
    return <p className="text-sm text-stone-600">Loading client…</p>;
  }

  if (clientQuery.error instanceof ApiError && clientQuery.error.status === 404) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">Client not found</h1>
        <p className="text-sm text-stone-600">
          This client does not exist or you do not have access to it.
        </p>
        <Link href="/clients" className="text-sm font-medium text-stone-900 underline">
          Back to clients
        </Link>
      </div>
    );
  }

  if (clientQuery.error) {
    return (
      <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
        {clientQuery.error instanceof Error
          ? clientQuery.error.message
          : "Failed to load client"}
      </p>
    );
  }

  const client = clientQuery.data;
  if (!client) {
    return null;
  }

  const trialBalances = trialBalancesQuery.data?.items ?? [];

  return (
    <div className="space-y-8">
      <div>
        <Link href="/clients" className="text-sm text-stone-600 hover:text-stone-900">
          ← Back to clients
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{client.name}</h1>
      </div>

      <div className="rounded border border-stone-200 bg-white p-4 text-sm">
        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-stone-400">
              Functional currency
            </dt>
            <dd className="mt-1 font-mono">{client.functional_currency}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-stone-400">Created</dt>
            <dd className="mt-1 text-stone-700">{formatDateTime(client.created_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-stone-400">
              Company number
            </dt>
            <dd className="mt-1 text-stone-700">
              {client.company_number ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-stone-400">Industry</dt>
            <dd className="mt-1 text-stone-700">{client.industry ?? "—"}</dd>
          </div>
        </dl>
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-lg font-semibold tracking-tight">Trial balances</h2>
          <Link
            href={`/upload?client=${client.id}`}
            className="rounded bg-stone-900 px-3 py-1.5 text-sm font-medium text-white"
          >
            Upload trial balance
          </Link>
        </div>

        {trialBalancesQuery.isLoading ? (
          <p className="text-sm text-stone-600">Loading trial balances…</p>
        ) : trialBalancesQuery.error ? (
          <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {trialBalancesQuery.error instanceof Error
              ? trialBalancesQuery.error.message
              : "Failed to load trial balances"}
          </p>
        ) : trialBalances.length === 0 ? (
          <p className="rounded border border-stone-200 bg-white px-4 py-6 text-sm text-stone-600">
            No trial balances uploaded yet.{" "}
            <Link
              href={`/upload?client=${client.id}`}
              className="font-medium text-stone-900 underline"
            >
              Upload a trial balance
            </Link>{" "}
            to get started.
          </p>
        ) : (
          <div className="overflow-x-auto rounded border border-stone-200 bg-white">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-stone-200 bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
                <tr>
                  <th className="px-3 py-2 font-medium">Period end</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {trialBalances.map((tb) => (
                  <tr key={tb.id} className="border-b border-stone-100">
                    <td colSpan={3} className="p-0">
                      <Link
                        href={`/dashboard/${tb.id}`}
                        className="grid grid-cols-3 gap-4 px-3 py-2 hover:bg-stone-50"
                      >
                        <span className="font-medium">
                          {formatDate(tb.period_end)}
                        </span>
                        <span>
                          <span className="rounded bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-700">
                            {tb.status}
                          </span>
                        </span>
                        <span className="text-stone-600">
                          {formatDateTime(tb.created_at)}
                        </span>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
