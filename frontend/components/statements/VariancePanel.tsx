"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/currency";
import {
  filterPriorTbOptions,
  readPreferredPriorTbId,
  writePreferredPriorTbId,
} from "@/lib/prior-period";
import { formatCanonicalLineLabel, formatDate } from "@/lib/utils";
import { VarianceCommentarySection } from "./VarianceCommentarySection";
import type {
  TrialBalanceListResponse,
  VarianceDirection,
  VarianceResponse,
} from "@/types";

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

async function fetchVariance(
  tbId: string,
  priorTbId: string | null,
  getToken: () => Promise<string | null>,
): Promise<VarianceResponse> {
  return apiFetch<VarianceResponse>(`/trial-balances/${tbId}/variance`, {
    method: "POST",
    getToken,
    body: JSON.stringify(priorTbId ? { prior_tb_id: priorTbId } : {}),
  });
}

function responseMatchesPrior(
  response: VarianceResponse | null | undefined,
  selectedPriorTbId: string,
): boolean {
  if (!response) return false;
  // Auto mode (empty selection): any response is acceptable until a prior is chosen.
  if (!selectedPriorTbId) return true;
  return response.prior_tb_id === selectedPriorTbId;
}

export function VariancePanel({
  tbId,
  currencyCode,
  companyId: companyIdProp = null,
  periodEnd: periodEndProp = null,
}: {
  tbId: string;
  currencyCode: string;
  /** From statements payload — lets prior options load before variance exists. */
  companyId?: string | null;
  periodEnd?: string | null;
}) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  /** Empty until bootstrap (GET / upload preference) resolves a prior id. */
  const [selectedPriorTbId, setSelectedPriorTbId] = useState<string>("");
  const [bootstrapDone, setBootstrapDone] = useState(false);

  // Stored analysis — used only to seed company/period/default prior.
  const storedQuery = useQuery({
    queryKey: ["tb-variance-stored", tbId],
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

  const companyId =
    companyIdProp ?? storedQuery.data?.company_id ?? null;
  const periodEnd =
    periodEndProp ?? storedQuery.data?.period_end ?? null;

  const priorsQuery = useQuery({
    queryKey: ["tb-prior-options", companyId, periodEnd],
    enabled: Boolean(companyId && periodEnd),
    queryFn: () =>
      apiFetch<TrialBalanceListResponse>(
        `/trial-balances?company_id=${encodeURIComponent(companyId!)}&limit=100`,
        { getToken },
      ),
  });

  const priorOptions = useMemo(() => {
    if (!periodEnd) return [];
    return filterPriorTbOptions(
      priorsQuery.data?.items ?? [],
      periodEnd,
      tbId,
    );
  }, [priorsQuery.data?.items, periodEnd, tbId]);

  // Seed selected prior: upload preference → stored analysis → auto (newest prior).
  useEffect(() => {
    if (bootstrapDone || storedQuery.isLoading) return;
    if (!companyId || !periodEnd) {
      // Still waiting on company/period from a successful stored GET, or no analysis yet.
      if (storedQuery.data === null && !storedQuery.isFetching) {
        // No stored variance and no company_id yet — need a generate pass without prior.
        setBootstrapDone(true);
      }
      return;
    }
    if (priorsQuery.isLoading) return;

    const preferred = readPreferredPriorTbId(companyId, periodEnd);
    const preferredValid =
      preferred && priorOptions.some((tb) => tb.id === preferred)
        ? preferred
        : null;
    const storedPrior = storedQuery.data?.prior_tb_id ?? null;
    const storedValid =
      storedPrior && priorOptions.some((tb) => tb.id === storedPrior)
        ? storedPrior
        : null;
    const autoPrior = priorOptions[0]?.id ?? "";
    const next = preferredValid || storedValid || autoPrior;
    setSelectedPriorTbId(next);
    setBootstrapDone(true);
  }, [
    bootstrapDone,
    storedQuery.isLoading,
    storedQuery.isFetching,
    storedQuery.data,
    companyId,
    periodEnd,
    priorsQuery.isLoading,
    priorOptions,
  ]);

  // Active variance: keyed by prior so a dropdown change is a distinct query.
  const varianceQuery = useQuery({
    queryKey: ["tb-variance", tbId, selectedPriorTbId || "auto"],
    enabled: bootstrapDone,
    queryFn: () =>
      fetchVariance(tbId, selectedPriorTbId || null, getToken),
    staleTime: 0,
  });

  const generateMutation = useMutation({
    mutationFn: (priorTbId: string | null) =>
      fetchVariance(tbId, priorTbId, getToken),
    onSuccess: (data, priorTbId) => {
      const keyPrior = data.prior_tb_id ?? priorTbId ?? "auto";
      queryClient.setQueryData(["tb-variance", tbId, keyPrior], data);
      queryClient.setQueryData(["tb-variance-stored", tbId], data);
      // Only sync selection from this response when it matches the request —
      // avoids a slow older mutation overwriting a newer dropdown choice.
      if (
        data.prior_tb_id &&
        (priorTbId === null || data.prior_tb_id === priorTbId)
      ) {
        setSelectedPriorTbId((current) =>
          current === "" || current === priorTbId || current === data.prior_tb_id
            ? data.prior_tb_id!
            : current,
        );
      }
      if (companyId && periodEnd && data.prior_tb_id) {
        writePreferredPriorTbId(companyId, periodEnd, data.prior_tb_id);
      }
    },
  });

  // CRITICAL: never fall back across priors. Old bug was
  // `generateMutation.data ?? varianceQuery.data` with queryKey missing
  // prior_tb_id — dropdown POSTed correctly but UI kept showing the previous
  // prior's amounts until (or unless) cache lined up.
  const data =
    (responseMatchesPrior(varianceQuery.data, selectedPriorTbId)
      ? varianceQuery.data
      : undefined) ??
    (generateMutation.variables === (selectedPriorTbId || null) &&
    responseMatchesPrior(generateMutation.data, selectedPriorTbId)
      ? generateMutation.data
      : undefined) ??
    (responseMatchesPrior(storedQuery.data, selectedPriorTbId)
      ? storedQuery.data
      : undefined);
  const isRefreshing =
    varianceQuery.isFetching ||
    (generateMutation.isPending &&
      generateMutation.variables === (selectedPriorTbId || null));
  const needsGenerate =
    bootstrapDone &&
    storedQuery.data === null &&
    !data &&
    !varianceQuery.isFetching &&
    !generateMutation.isPending &&
    priorOptions.length === 0;

  const onPriorChange = (next: string) => {
    setSelectedPriorTbId(next);
    if (companyId && periodEnd) {
      writePreferredPriorTbId(companyId, periodEnd, next || null);
    }
    // Query key change triggers varianceQuery; also POST immediately so network
    // evidence is obvious and we don't wait on background refetch timing.
    generateMutation.mutate(next || null);
  };

  if (storedQuery.isLoading && !bootstrapDone) {
    return <p className="text-sm text-soft">Loading variance analysis…</p>;
  }

  if (storedQuery.error && !data) {
    return (
      <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        {storedQuery.error instanceof Error
          ? storedQuery.error.message
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
          onClick={() => generateMutation.mutate(null)}
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
    if (isRefreshing || !bootstrapDone) {
      // Keep the prior selector visible while a new prior's POST is in flight —
      // otherwise the dropdown vanishes and it looks like nothing happened.
      if (bootstrapDone && priorOptions.length > 0) {
        return (
          <div className="space-y-4">
            <div className="flex min-w-[16rem] flex-col gap-1.5">
              <label
                htmlFor="variance-prior-tb"
                className="text-xs font-semibold uppercase tracking-[0.12em] text-soft"
              >
                Compare against
              </label>
              <select
                id="variance-prior-tb"
                data-testid="variance-prior-select"
                value={selectedPriorTbId}
                disabled={isRefreshing}
                onChange={(event) => onPriorChange(event.target.value)}
                className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink shadow-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50"
              >
                {priorOptions.map((tb, index) => (
                  <option key={tb.id} value={tb.id}>
                    {formatDate(tb.period_end)}
                    {index === 0 ? " (auto)" : ""}
                  </option>
                ))}
              </select>
            </div>
            <p className="text-sm text-soft" role="status">
              Loading variance for selected prior…
            </p>
          </div>
        );
      }
      return <p className="text-sm text-soft">Loading variance analysis…</p>;
    }
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

  const selectedPrior = priorOptions.find((tb) => tb.id === selectedPriorTbId);
  const autoPriorId = priorOptions[0]?.id ?? null;
  const isAutoSelection =
    Boolean(autoPriorId) && selectedPriorTbId === autoPriorId;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-[16rem] flex-1 flex-col gap-1.5">
          <label
            htmlFor="variance-prior-tb"
            className="text-xs font-semibold uppercase tracking-[0.12em] text-soft"
          >
            Compare against
          </label>
          <select
            id="variance-prior-tb"
            data-testid="variance-prior-select"
            value={selectedPriorTbId}
            disabled={isRefreshing || priorOptions.length === 0}
            onChange={(event) => onPriorChange(event.target.value)}
            className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink shadow-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50"
          >
            {priorOptions.length === 0 ? (
              <option value="">No prior periods available</option>
            ) : (
              priorOptions.map((tb, index) => (
                <option key={tb.id} value={tb.id}>
                  {formatDate(tb.period_end)}
                  {index === 0 ? " (auto)" : ""}
                </option>
              ))
            )}
          </select>
          <p className="text-xs text-soft" data-testid="variance-prior-hint">
            {selectedPrior
              ? isAutoSelection
                ? `Auto-detected most recent prior (${formatDate(selectedPrior.period_end)}).`
                : `Comparing to ${formatDate(selectedPrior.period_end)}.`
              : companyId
                ? "Select a prior trial balance to compare."
                : "Run or refresh variance to load prior-period options."}
            {data.prior_tb_id ? (
              <span className="ml-1 font-mono text-[10px] text-soft/80">
                prior={data.prior_tb_id.slice(0, 8)}
              </span>
            ) : null}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
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
            disabled={isRefreshing}
            onClick={() => generateMutation.mutate(selectedPriorTbId || null)}
            className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
          >
            {isRefreshing ? "Refreshing…" : "Refresh variance"}
          </button>
        </div>
      </div>

      {generateMutation.error || varianceQuery.error ? (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {(generateMutation.error ?? varianceQuery.error) instanceof Error
            ? (generateMutation.error ?? varianceQuery.error)!.message
            : "Refresh failed"}
        </p>
      ) : null}

      {isRefreshing && !data.items.length ? (
        <p className="text-sm text-soft">Refreshing variance…</p>
      ) : null}

      {data.items.length === 0 ? (
        <p className="text-sm text-soft">No variance lines returned.</p>
      ) : (
        <div
          className="overflow-x-auto rounded-md border border-line bg-surface-elevated"
          data-testid="variance-table"
          data-prior-tb-id={data.prior_tb_id ?? ""}
        >
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
                    data-testid={
                      item.line_item_code === "revenue"
                        ? "variance-revenue-prior"
                        : undefined
                    }
                  >
                    {formatCurrency(item.prior_amount, currencyCode)}
                  </td>
                  <td
                    className={`px-4 py-2.5 text-right tabular-nums font-medium text-ink ${amountClass(
                      item.variance_amount,
                    )}`}
                    data-testid={
                      item.line_item_code === "revenue"
                        ? "variance-revenue-var"
                        : undefined
                    }
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

      <VarianceCommentarySection variance={data} />
    </div>
  );
}