"use client";

/**
 * Right slide-over: evidence-graph drill-down for one statement face line.
 *
 * Data: GET /trial-balances/{tbId}/statements/lines/{lineId}/sources
 * Stacking: exclusive with Copilot — opener closes Ask; Ask open closes this.
 * Read-only — no edits, formulae, or add-line (see tracked-gaps).
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef } from "react";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/currency";
import type { StatementLineSourcesResponse } from "@/types";

function amountsDiffer(a: string, b: string): boolean {
  const left = Number.parseFloat(a);
  const right = Number.parseFloat(b);
  if (!Number.isFinite(left) || !Number.isFinite(right)) return true;
  return Math.abs(left - right) > 0.01;
}

export function StatementLineDrilldown({
  open,
  tbId,
  lineId,
  onClose,
}: {
  open: boolean;
  tbId: string;
  lineId: string | null;
  onClose: () => void;
}) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const { getToken } = useAuth();

  const sourcesQuery = useQuery({
    queryKey: ["statement-line-sources", tbId, lineId],
    enabled: open && Boolean(lineId),
    queryFn: () =>
      apiFetch<StatementLineSourcesResponse>(
        `/trial-balances/${tbId}/statements/lines/${lineId}/sources`,
        { getToken },
      ),
  });

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !lineId) return null;

  const data = sourcesQuery.data;
  const currency = data?.functional_currency ?? "GBP";
  const loading = sourcesQuery.isLoading || sourcesQuery.isFetching;
  const error =
    sourcesQuery.error instanceof Error
      ? sourcesQuery.error.message
      : sourcesQuery.isError
        ? "Could not load source accounts"
        : null;

  return (
    <>
      <button
        type="button"
        aria-label="Close statement line detail"
        className="fixed inset-0 z-[60] bg-ink/30 transition-opacity"
        onClick={onClose}
        data-testid="statement-line-drilldown-backdrop"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid="statement-line-drilldown"
        className="fixed inset-y-0 right-0 z-[80] flex h-full w-full max-w-none flex-col border-l border-line bg-surface-elevated shadow-xl sm:max-w-lg md:max-w-xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
              Source accounts
            </p>
            <h2
              id={titleId}
              className="mt-1 font-display text-lg font-semibold text-ink"
              data-testid="statement-line-drilldown-title"
            >
              {data?.line_item_name ?? "Statement line"}
            </h2>
            {data ? (
              <div className="mt-3 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <p
                  className={`font-display text-2xl font-semibold tabular-nums tracking-tight ${
                    Number.parseFloat(data.amount) < 0
                      ? "text-red-800"
                      : "text-ink"
                  }`}
                  data-testid="statement-line-drilldown-amount"
                >
                  {formatCurrency(data.amount, currency)}
                </p>
                <span className="text-sm text-soft">
                  {data.statement_type}
                  {data.is_subtotal ? " · subtotal" : ""}
                </span>
              </div>
            ) : null}
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-sm font-semibold text-soft transition-colors hover:bg-accent-muted hover:text-accent"
            data-testid="statement-line-drilldown-close"
          >
            Close
          </button>
        </header>

        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
          {loading ? (
            <p className="text-sm text-soft" data-testid="statement-line-drilldown-loading">
              Loading source accounts…
            </p>
          ) : null}
          {error ? (
            <p
              className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
              data-testid="statement-line-drilldown-error"
            >
              {error}
            </p>
          ) : null}

          {data && !loading ? (
            <>
              {data.sources.length === 0 ? (
                <p
                  className="text-sm text-ink-secondary"
                  data-testid="statement-line-drilldown-empty"
                >
                  No direct trial-balance accounts are linked to this line. It
                  may be computed from other statement lines (for example a
                  roll-forward or nil-filtered leaf).
                </p>
              ) : (
                <div className="overflow-x-auto rounded-md border border-line">
                  <table
                    className="min-w-full text-left text-sm"
                    data-testid="statement-line-drilldown-table"
                  >
                    <thead className="border-b border-line bg-accent-muted/50 text-xs uppercase tracking-[0.12em] text-soft">
                      <tr>
                        <th className="px-3 py-2.5 font-semibold">Code</th>
                        <th className="px-3 py-2.5 font-semibold">Account</th>
                        <th className="px-3 py-2.5 text-right font-semibold">
                          Face
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.sources.map((source) => {
                        const face = Number.parseFloat(source.face_amount);
                        const negative =
                          Number.isFinite(face) && face < 0;
                        return (
                          <tr
                            key={source.mapping_id}
                            className="border-b border-line/70"
                            data-testid={`statement-line-source-${source.mapping_id}`}
                          >
                            <td className="px-3 py-2 font-mono text-xs text-ink-secondary">
                              {source.account_code || "—"}
                            </td>
                            <td className="px-3 py-2 text-ink">
                              <span className="block">
                                {source.account_name}
                              </span>
                              <span className="mt-0.5 block text-xs text-soft">
                                {source.canonical_line}
                              </span>
                            </td>
                            <td
                              className={`px-3 py-2 text-right tabular-nums ${
                                negative ? "text-red-800" : "text-ink"
                              }`}
                            >
                              {formatCurrency(source.face_amount, currency)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                    <tfoot>
                      <tr className="bg-accent-muted/40">
                        <td
                          colSpan={2}
                          className="px-3 py-2.5 text-sm font-semibold text-ink"
                        >
                          Sources total ({data.sources.length})
                        </td>
                        <td
                          className={`px-3 py-2.5 text-right text-sm font-semibold tabular-nums ${
                            Number.parseFloat(data.sources_face_total) < 0
                              ? "text-red-800"
                              : "text-ink"
                          }`}
                          data-testid="statement-line-drilldown-sources-total"
                        >
                          {formatCurrency(data.sources_face_total, currency)}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              )}

              {data.sources.length > 0 &&
              amountsDiffer(data.amount, data.sources_face_total) ? (
                <p
                  className="text-xs text-soft"
                  data-testid="statement-line-drilldown-reconcile-note"
                >
                  Sources total differs from the statement face amount. That can
                  happen on computed or roll-forward lines where provenance is
                  partial.
                </p>
              ) : null}

              <p className="text-xs text-soft">
                Read-only evidence graph. Editing statement lines or adding
                formulae is not available yet.
              </p>
            </>
          ) : null}
        </div>
      </aside>
    </>
  );
}
