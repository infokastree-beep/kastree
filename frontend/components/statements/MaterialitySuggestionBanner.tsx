"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/currency";
import type { MaterialitySuggestionResponse } from "@/types";

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
    },
  });

  const dismissMutation = useMutation({
    mutationFn: async (companyId: string) =>
      apiFetch(`/companies/${companyId}/materiality-suggestion/dismiss`, {
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

  const absLabel = formatCurrency(data.suggested_abs, currencyCode);
  const pending = applyMutation.isPending || dismissMutation.isPending;

  return (
    <div
      className="rounded-md border border-accent/30 bg-accent-muted/40 px-4 py-3"
      data-testid="materiality-suggestion-banner"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink">
            Materiality suggestion
          </p>
          <p className="mt-1 text-sm text-ink-secondary">
            We suggest {data.suggested_pct}% ({absLabel}) based on your figures
            — apply it?
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
            {applyMutation.isPending ? "Applying…" : "Apply"}
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
        </div>
      </div>
    </div>
  );
}
