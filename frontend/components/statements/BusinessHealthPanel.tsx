"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import type { BusinessHealthResponse } from "@/types";

function confidenceCaption(confidence: string | null | undefined): string {
  if (!confidence) return "Confidence unknown";
  return `${confidence.charAt(0).toUpperCase()}${confidence.slice(1)} confidence`;
}

export function BusinessHealthPanel({ tbId }: { tbId: string }) {
  const { getToken } = useAuth();

  const healthQuery = useQuery({
    queryKey: ["tb-business-health", tbId],
    queryFn: () =>
      apiFetch<BusinessHealthResponse>(
        `/trial-balances/${tbId}/business-health`,
        { method: "POST", getToken, body: JSON.stringify({}) },
      ),
  });

  if (healthQuery.isLoading) {
    return (
      <div
        className="rounded-md border border-line bg-surface-elevated p-5"
        data-testid="business-health-loading"
      >
        <h2 className="font-display text-base font-semibold text-ink">
          Business health
        </h2>
        <p className="mt-2 text-sm text-soft">Drafting executive summary…</p>
      </div>
    );
  }

  if (healthQuery.error) {
    return (
      <div
        className="rounded-md border border-red-200 bg-red-50 p-5"
        data-testid="business-health-error"
      >
        <h2 className="font-display text-base font-semibold text-ink">
          Business health
        </h2>
        <p className="mt-2 text-sm text-red-800">
          {healthQuery.error instanceof Error
            ? healthQuery.error.message
            : "Could not load business health summary"}
          {healthQuery.error instanceof ApiError && healthQuery.error.status === 400
            ? " — generate statements first."
            : null}
        </p>
      </div>
    );
  }

  const data = healthQuery.data;
  if (!data) return null;

  if (!data.available) {
    return (
      <div
        className="rounded-md border border-line bg-surface-elevated p-5"
        data-testid="business-health-unavailable"
      >
        <h2 className="font-display text-base font-semibold text-ink">
          Business health
        </h2>
        <p className="mt-2 text-sm text-ink-secondary">
          {data.message ??
            "Not enough history yet — upload a prior period trial balance to enable the business health summary."}
        </p>
      </div>
    );
  }

  const health = data.health;
  const points = health?.key_points?.filter((p) => p.trim()) ?? [];
  const summary = health?.summary?.trim() ?? "";

  if (!summary && points.length === 0) {
    return (
      <div
        className="rounded-md border border-line bg-surface-elevated p-5"
        data-testid="business-health-empty"
      >
        <h2 className="font-display text-base font-semibold text-ink">
          Business health
        </h2>
        <p className="mt-2 text-sm text-ink-secondary">
          AI commentary temporarily unavailable. Statements are complete —
          refresh to retry the executive summary. Amounts are never sent to the
          model.
        </p>
      </div>
    );
  }

  return (
    <section
      className="rounded-md border border-line bg-surface-elevated p-5"
      data-testid="business-health-panel"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-display text-base font-semibold text-ink">
            Business health
          </h2>
          <p className="mt-1 text-sm text-ink-secondary">
            Three-bullet executive read from directional trends — gross margin,
            operating leverage, cash, and debt. No monetary amounts are sent to
            the model.
          </p>
        </div>
        <p className="text-xs text-soft" data-testid="business-health-confidence">
          {confidenceCaption(health?.confidence)}
          {health?.is_edited ? " · Edited" : " · AI draft"}
        </p>
      </div>

      {summary ? (
        <p
          className="mt-4 text-sm leading-relaxed text-ink"
          data-testid="business-health-summary"
        >
          {summary}
        </p>
      ) : null}

      {points.length > 0 ? (
        <ol
          className="mt-3 list-decimal space-y-2 pl-5 text-sm text-ink-secondary"
          data-testid="business-health-key-points"
        >
          {points.map((point, index) => (
            <li key={`${index}-${point.slice(0, 24)}`}>{point}</li>
          ))}
        </ol>
      ) : null}

      {health?.reasoning?.trim() ? (
        <p className="mt-3 text-xs text-soft" title={health.reasoning}>
          Model notes available on hover of this line.
        </p>
      ) : null}
    </section>
  );
}
