"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { CompanyEntityForm } from "@/components/clients/CompanyEntityForm";
import type { CompanyEntityFormValues } from "@/lib/company-form";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { createCompanyEntity } from "@/lib/companies";
import { formatDate, formatDateTime } from "@/lib/utils";
import type {
  CompanyListResponse,
  IClient,
  ICompany,
  TrialBalanceListResponse,
  TrialBalanceResponse,
} from "@/types";

const TB_PAGE_SIZE = 20;

/**
 * Route each TB to its current workflow step:
 * - mapping / failed / still parsing → /mapping/{id}
 * - validating onward (statements may exist or be generatable) → /dashboard/{id}
 */
function trialBalanceHref(tb: { id: string; status: string }): string {
  const status = tb.status;
  if (
    status === "complete" ||
    status === "validating" ||
    status === "generating" ||
    status === "analysing"
  ) {
    return `/dashboard/${tb.id}`;
  }
  return `/mapping/${tb.id}`;
}

function CompanyTrialBalances({ company }: { company: ICompany }) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const trialBalancesQuery = useQuery({
    queryKey: ["trial-balances", company.id],
    queryFn: () =>
      apiFetch<TrialBalanceListResponse>(
        `/trial-balances?company_id=${company.id}&limit=${TB_PAGE_SIZE}`,
        { getToken },
      ),
  });

  const deleteMutation = useMutation({
    mutationFn: (tbId: string) =>
      apiFetch<TrialBalanceResponse>(`/trial-balances/${tbId}`, {
        method: "DELETE",
        getToken,
      }),
    onSuccess: () => {
      setPendingDeleteId(null);
      void queryClient.invalidateQueries({ queryKey: ["trial-balances", company.id] });
    },
  });

  const trialBalances = trialBalancesQuery.data?.items ?? [];

  return (
    <div className="space-y-3 rounded border border-stone-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-stone-900">{company.name}</h3>
          <p className="mt-0.5 text-sm text-stone-600">
            <span className="font-mono text-xs">{company.functional_currency}</span>
            {company.company_number ? (
              <>
                {" "}
                · Co. no. {company.company_number}
              </>
            ) : null}
          </p>
        </div>
        <Link
          href={`/upload?company=${company.id}`}
          className="rounded bg-stone-900 px-3 py-1.5 text-sm font-medium text-white"
        >
          Upload trial balance
        </Link>
      </div>

      {deleteMutation.error ? (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {deleteMutation.error instanceof Error
            ? deleteMutation.error.message
            : "Failed to delete trial balance"}
        </p>
      ) : null}

      {trialBalancesQuery.isLoading ? (
        <p className="text-sm text-stone-600">Loading trial balances…</p>
      ) : trialBalancesQuery.error ? (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {trialBalancesQuery.error instanceof Error
            ? trialBalancesQuery.error.message
            : "Failed to load trial balances"}
        </p>
      ) : trialBalances.length === 0 ? (
        <p className="text-sm text-stone-600">
          No trial balances yet.{" "}
          <Link
            href={`/upload?company=${company.id}`}
            className="font-medium text-stone-900 underline"
          >
            Upload one
          </Link>
          .
        </p>
      ) : (
        <div className="overflow-x-auto rounded border border-stone-100">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-stone-200 bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
              <tr>
                <th className="px-3 py-2 font-medium">Period end</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Uploaded</th>
                <th className="px-3 py-2 font-medium">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {trialBalances.map((tb) => (
                <tr key={tb.id} className="border-b border-stone-100">
                  <td className="p-0">
                    <Link
                      href={trialBalanceHref(tb)}
                      className="block px-3 py-2 font-medium hover:bg-stone-50"
                    >
                      {formatDate(tb.period_end)}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    <span className="rounded bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-700">
                      {tb.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-stone-600">
                    {formatDateTime(tb.created_at)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {pendingDeleteId === tb.id ? (
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <button
                          type="button"
                          disabled={deleteMutation.isPending}
                          onClick={() => deleteMutation.mutate(tb.id)}
                          className="rounded bg-red-800 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
                        >
                          {deleteMutation.isPending ? "Deleting…" : "Confirm"}
                        </button>
                        <button
                          type="button"
                          disabled={deleteMutation.isPending}
                          onClick={() => {
                            setPendingDeleteId(null);
                            deleteMutation.reset();
                          }}
                          className="rounded border border-stone-200 px-2 py-1 text-xs font-medium text-stone-700"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setPendingDeleteId(tb.id)}
                        className="rounded border border-red-200 px-2 py-1 text-xs font-medium text-red-800 hover:bg-red-50"
                      >
                        Delete
                      </button>
                    )}
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

export function ClientDetail({ clientId }: { clientId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { getToken } = useAuth();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showAddCompany, setShowAddCompany] = useState(false);

  const clientQuery = useQuery({
    queryKey: ["client", clientId],
    queryFn: () => apiFetch<IClient>(`/clients/${clientId}`, { getToken }),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 2,
  });

  const companiesQuery = useQuery({
    queryKey: ["companies", clientId],
    queryFn: () =>
      apiFetch<CompanyListResponse>(`/clients/${clientId}/companies`, { getToken }),
    enabled: clientQuery.isSuccess,
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 2,
  });

  const deleteMutation = useMutation({
    mutationFn: () =>
      apiFetch<IClient>(`/clients/${clientId}`, {
        method: "DELETE",
        getToken,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["clients"] });
      router.push("/clients");
    },
  });

  const addCompanyMutation = useMutation({
    mutationFn: (values: CompanyEntityFormValues) =>
      createCompanyEntity(clientId, values, getToken),
    onSuccess: () => {
      setShowAddCompany(false);
      void queryClient.invalidateQueries({ queryKey: ["companies", clientId] });
      void queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
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

  const companies = companiesQuery.data?.items ?? [];
  const addCompanyError =
    addCompanyMutation.error instanceof Error ? addCompanyMutation.error.message : null;

  return (
    <div className="space-y-8">
      <div>
        <Link href="/clients" className="text-sm text-stone-600 hover:text-stone-900">
          ← Back to clients
        </Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{client.name}</h1>
          {!showDeleteConfirm ? (
            <button
              type="button"
              onClick={() => setShowDeleteConfirm(true)}
              className="rounded border border-red-200 px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-50"
            >
              Delete client
            </button>
          ) : null}
        </div>
      </div>

      {showDeleteConfirm ? (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-950">
          <p className="font-medium">Delete {client.name}?</p>
          <p className="mt-1">
            This removes the client from your list. Their data is archived and no
            longer appears in Kastree.
          </p>
          {deleteMutation.error ? (
            <p className="mt-2 text-red-800">
              {deleteMutation.error instanceof Error
                ? deleteMutation.error.message
                : "Delete failed"}
            </p>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
              className="rounded bg-red-800 px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {deleteMutation.isPending ? "Deleting…" : "Yes, delete client"}
            </button>
            <button
              type="button"
              disabled={deleteMutation.isPending}
              onClick={() => {
                setShowDeleteConfirm(false);
                deleteMutation.reset();
              }}
              className="rounded border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-900 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      <div className="rounded border border-stone-200 bg-white p-4 text-sm">
        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-stone-400">Created</dt>
            <dd className="mt-1 text-stone-700">{formatDateTime(client.created_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-stone-400">Companies</dt>
            <dd className="mt-1 text-stone-700">
              {companiesQuery.isLoading
                ? "…"
                : `${companies.length} ${companies.length === 1 ? "company" : "companies"}`}
            </dd>
          </div>
        </dl>
      </div>

      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold tracking-tight">Companies</h2>
          {!showAddCompany ? (
            <button
              type="button"
              onClick={() => setShowAddCompany(true)}
              className="rounded bg-stone-900 px-3 py-1.5 text-sm font-medium text-white"
            >
              + Add company
            </button>
          ) : null}
        </div>

        {showAddCompany ? (
          <div className="rounded border border-stone-200 bg-white p-4">
            <CompanyEntityForm
              intro={
                <p className="text-sm text-stone-600">
                  Add a company entity to{" "}
                  <span className="font-medium text-stone-900">{client.name}</span>.
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

        {companiesQuery.isLoading ? (
          <p className="text-sm text-stone-600">Loading companies…</p>
        ) : companiesQuery.error ? (
          <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {companiesQuery.error instanceof Error
              ? companiesQuery.error.message
              : "Failed to load companies"}
          </p>
        ) : companies.length === 0 && !showAddCompany ? (
          <div className="rounded border border-stone-200 bg-white px-4 py-6 text-sm text-stone-600">
            <p>No companies yet for this client group.</p>
            <button
              type="button"
              onClick={() => setShowAddCompany(true)}
              className="mt-3 rounded bg-stone-900 px-3 py-1.5 text-sm font-medium text-white"
            >
              + Add company
            </button>
          </div>
        ) : companies.length > 0 ? (
          <div className="space-y-4">
            {companies.map((company) => (
              <CompanyTrialBalances key={company.id} company={company} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
