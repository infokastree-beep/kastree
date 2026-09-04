"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/currency";
import { formatCanonicalLineLabel } from "@/lib/utils";
import type { VarianceDirection, VarianceResponse } from "@/types";

function formatPct(value: string | null): string {
  if (value === null || value === "") return "—";
  const numeric = Number.parseFloat(value);
  if (!Number.isFinite(numeric)) return value;
  return `${numeric.toFixed(1)}%`;
}

function directionLabel(direction: VarianceDirection): string {
  switch (direction) {
    case "increase":
      return "Increase";
    case "decrease":
      return "Decrease";
    case "new":
      return "New";
    case "removed":
      return "Removed";
    default:
      return direction;
  }
}

function directionClass(direction: VarianceDirection): string {
  switch (direction) {
    case "increase":
      return "text-accent";
    case "decrease":
      return "text-red-800";
    case "new":
      return "text-amber-900";
    case "removed":
      return "text-soft";
    default:
      return "text-ink";
  }
}

function amountClass(amount: string): string {
  const numeric = Number.parseFloat(amount);
  return Number.isFinite(numeric) && numeric < 0 ? "text-red-800" : "";
}

export function VariancePanel({
  tbId,
  currencyCode,
}: {
  tbId: string;
  currencyCode: string;
}) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  const varianceQuery = useQuery({
    queryKey: ["tb-variance", tbId],
    queryFn: async (): Promise<VarianceResponse | null> => {
      try {
        return await apiFetch<VarianceResponse>(
          `/trial-balances/${tbId}/variance`,
          { getToken },
        );
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          return null;
        }
        throw err;
      }
    },
  });

  const generateMutation = useMutation({
    mutationFn: () =>
      apiFetch<VarianceResponse>(`/trial-balances/${tbId}/variance`, {
        method: "POST",
        getToken,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["tb-variance", tbId], data);
    },
  });

  const data = generateMutation.data ?? varianceQuery.data;
  const needsGenerate = varianceQuery.data === null && !generateMutation.data;

  if (varianceQuery.isLoading) {
    return <p className="text-sm text-soft">Loading variance analysis…</p>;
  }

  if (varianceQuery.error && !generateMutation.data) {
    return (
      <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        {varianceQuery.error instanceof Error
          ? varianceQuery.error.message
          : "Failed to load variance analysis"}
      </p>
    );
  }

  if (needsGenerate) {
    return (
      <div className="space-y-4 rounded-md border border-line bg-surface-elevated p-6">
        <p className="text-sm text-ink-secondary">
          Variance analysis has not been run for this trial balance yet. A prior
          period with generated statements is required.
        </p>
        {generateMutation.error ? (
          <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {generateMutation.error instanceof Error
              ? generateMutation.error.message
              : "Variance analysis failed"}
          </p>
        ) : null}
        <button
          type="button"
          disabled={generateMutation.isPending}
          onClick={() => generateMutation.mutate()}
          className="rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {generateMutation.isPending
            ? "Running analysis…"
            : "Run variance analysis"}
        </button>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  if (!data.variance_available) {
    return (
      <div className="space-y-3 rounded-md border border-line bg-surface-elevated p-6">
        <p className="text-sm text-ink-secondary">
          {data.message ??
            "Upload prior period TB to enable variance analysis."}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-secondary">
          Material when ≥{" "}
          <span className="font-mono font-medium text-ink">
            {data.materiality_threshold_pct ?? "—"}%
          </span>{" "}
          or{" "}
          <span className="font-mono font-medium text-ink">
            {data.materiality_threshold_abs
              ? formatCurrency(data.materiality_threshold_abs, currencyCode)
              : "—"}
          </span>
        </p>
        <button
          type="button"
          disabled={generateMutation.isPending}
          onClick={() => generateMutation.mutate()}
          className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
        >
          {generateMutation.isPending ? "Refreshing…" : "Refresh variance"}
        </button>
      </div>

      {generateMutation.error ? (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {generateMutation.error instanceof Error
            ? generateMutation.error.message
            : "Refresh failed"}
        </p>
      ) : null}

      {data.items.length === 0 ? (
        <p className="text-sm text-soft">No variance lines returned.</p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-line bg-surface-elevated">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-line bg-accent-muted/50 text-xs uppercase tracking-[0.12em] text-soft">
              <tr>
                <th className="px-4 py-3 font-semibold">Line item</th>
                <th className="px-4 py-3 text-right font-semibold">Current</th>
                <th className="px-4 py-3 text-right font-semibold">Prior</th>
                <th className="px-4 py-3 text-right font-semibold">Variance</th>
                <th className="px-4 py-3 text-right font-semibold">%</th>
                <th className="px-4 py-3 font-semibold">Direction</th>
                <th className="px-4 py-3 font-semibold">Material</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr
                  key={item.line_item_code}
                  className={`border-b border-line/70 ${
                    item.is_material ? "bg-amber-50/70" : "bg-surface-elevated"
                  }`}
                >
                  <td className="px-4 py-2.5 font-medium text-ink">
                    {item.line_item_name ||
                      formatCanonicalLineLabel(item.line_item_code)}
                  </td>
                  <td
                    className={`px-4 py-2.5 text-right tabular-nums text-ink ${amountClass(
                      item.current_amount,
                    )}`}
                  >
                    {formatCurrency(item.current_amount, currencyCode)}
                  </td>
                  <td
                    className={`px-4 py-2.5 text-right tabular-nums text-ink ${amountClass(
                      item.prior_amount,
                    )}`}
                  >
                    {formatCurrency(item.prior_amount, currencyCode)}
                  </td>
                  <td
                    className={`px-4 py-2.5 text-right tabular-nums font-medium text-ink ${amountClass(
                      item.variance_amount,
                    )}`}
                  >
                    {formatCurrency(item.variance_amount, currencyCode)}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-ink-secondary">
                    {formatPct(item.variance_pct)}
                  </td>
                  <td
                    className={`px-4 py-2.5 font-medium ${directionClass(
                      item.direction,
                    )}`}
                  >
                    {directionLabel(item.direction)}
                  </td>
                  <td className="px-4 py-2.5">
                    {item.is_material ? (
                      <span className="rounded-md bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-950">
                        Yes
                      </span>
                    ) : (
                      <span className="text-soft">No</span>
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
