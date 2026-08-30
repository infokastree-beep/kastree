"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import type { ClientListResponse } from "@/types";

export function ClientsList() {
  const { getToken } = useAuth();

  const clientsQuery = useQuery({
    queryKey: ["clients"],
    queryFn: () =>
      apiFetch<ClientListResponse>("/clients?limit=100", { getToken }),
  });

  if (clientsQuery.isLoading) {
    return <p className="text-sm text-stone-600">Loading clients…</p>;
  }

  if (clientsQuery.error) {
    return (
      <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
        {clientsQuery.error instanceof Error
          ? clientsQuery.error.message
          : "Failed to load clients"}
      </p>
    );
  }

  const clients = clientsQuery.data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Clients</h1>
          <p className="mt-1 text-sm text-stone-600">
            {clientsQuery.data?.total ?? 0} client
            {(clientsQuery.data?.total ?? 0) === 1 ? "" : "s"} in your practice.
          </p>
        </div>
        <Link
          href="/clients/new"
          className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white"
        >
          + New client
        </Link>
      </div>

      {clients.length === 0 ? (
        <p className="rounded border border-stone-200 bg-white px-4 py-6 text-sm text-stone-600">
          No clients yet.{" "}
          <Link href="/clients/new" className="font-medium text-stone-900 underline">
            Create your first client
          </Link>{" "}
          to start uploading trial balances.
        </p>
      ) : (
        <div className="overflow-x-auto rounded border border-stone-200 bg-white">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-stone-200 bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
              <tr>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Currency</th>
                <th className="px-3 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((client) => (
                <tr key={client.id} className="border-b border-stone-100">
                  <td className="px-3 py-2 font-medium">{client.name}</td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {client.functional_currency}
                  </td>
                  <td className="px-3 py-2 text-stone-600">
                    {formatDateTime(client.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
