"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/currency";
import type { ICompany, MaterialitySuggestionResponse } from "@/types";

export function MaterialitySuggestionBanner({
  tbId,
  currencyCode,
}: {
  tbId: string;
  currencyCode: string;
}) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  const suggestionQuery = useQuery({
    queryKey: ["tb-materiality-suggestion", tbId],
    queryFn: () =>
      apiFetch<MaterialitySuggestionResponse>(
        `/trial-balances/${tbId}/materiality-suggestion`,
        { getToken },
      ),
  });

  const companyId = suggestionQuery.data?.company_id;
  const companyQuery = useQuery({
    queryKey: ["company", companyId],
    enabled: Boolean(companyId),
    queryFn: () =>
      apiFetch<ICompany>(`/companies/${companyId}`, { getToken }),
  });
  const clientId = companyQuery.data?.client_id ?? null;

  const applyMutation = useMutation({
    mutationFn: async (suggestion: MaterialitySuggestionResponse) => {
      if (!suggestion.suggested_pct || !suggestion.suggested_abs) {
        throw new Error("Suggestion is incomplete");
      }
      return apiFetch(`/companies/${suggestion.company_id}`, {
        method: "PUT",
        getToken,
        body: JSON.stringify({
          materiality_threshold_pct: suggestion.suggested_pct,
          materiality_threshold_abs: suggestion.suggested_abs,
        }),
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["tb-materiality-suggestion", tbId],
      });
      void queryClient.invalidateQueries({ queryKey: ["tb-variance", tbId] });
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
    },
  });

  const dismissMutation = useMutation({
    mutationFn: async (dismissCompanyId: string) =>
      apiFetch(`/companies/${dismissCompanyId}/materiality-suggestion/dismiss`, {
        method: "POST",
        getToken,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["tb-materiality-suggestion", tbId],
      });
    },
  });

  const data = suggestionQuery.data;
  if (!data?.available || !data.suggested_pct || !data.suggested_abs) {
    return null;
  }

  const suggestedAbsLabel = formatCurrency(data.suggested_abs, currencyCode);
  const currentAbsLabel = formatCurrency(data.current_abs, currencyCode);
  const pctAlreadyMatches =
    Number(data.current_pct) === Number(data.suggested_pct);
  const pending = applyMutation.isPending || dismissMutation.isPending;
  const bodyText =
    data.message ??
    (pctAlreadyMatches
      ? `Your materiality % is already ${data.current_pct}%, but the absolute threshold (${currentAbsLabel}) is out of date — update absolute to ${suggestedAbsLabel}?`
      : `We suggest ${data.suggested_pct}% (${suggestedAbsLabel}) based on your figures — apply it?`);

  return (
    <div
      className="rounded-md border border-accent/30 bg-accent-muted/40 px-4 py-3"
      data-testid="materiality-suggestion-banner"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink">Materiality suggestion</p>
          <p className="mt-1 text-sm text-ink-secondary">{bodyText}</p>
          <p className="mt-1 text-xs text-soft">
            Current: {data.current_pct}% / {currentAbsLabel} · Suggested:{" "}
            {data.suggested_pct}% / {suggestedAbsLabel}
          </p>
          <p className="mt-1 text-xs text-soft">{data.disclaimer}</p>
          {applyMutation.error || dismissMutation.error ? (
            <p className="mt-2 text-sm text-red-800">
              {(applyMutation.error || dismissMutation.error) instanceof Error
                ? (applyMutation.error || dismissMutation.error)!.message
                : "Could not update materiality"}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={pending}
            onClick={() => applyMutation.mutate(data)}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover disabled:opacity-50"
            data-testid="materiality-suggestion-apply"
          >
            {applyMutation.isPending
              ? "Updating…"
              : pctAlreadyMatches
                ? "Update absolute"
                : "Apply"}
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={() => dismissMutation.mutate(data.company_id)}
            className="rounded-md border border-line bg-surface-elevated px-3 py-1.5 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
            data-testid="materiality-suggestion-dismiss"
          >
            Not now
          </button>
          {clientId ? (
            <Link
              href={`/clients/${clientId}#materiality-${data.company_id}`}
              className="rounded-md px-3 py-1.5 text-sm font-semibold text-accent underline-offset-2 hover:underline"
              data-testid="materiality-suggestion-edit-link"
            >
              Edit manually
            </Link>
          ) : null}
        </div>
      </div>
    </div>
  );
}
