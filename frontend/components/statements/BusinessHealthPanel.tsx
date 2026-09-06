"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import type { BusinessHealthResponse } from "@/types";

function confidenceCaption(confidence: string | null | undefined): string {
  if (!confidence) return "Confidence unknown";
  return `${confidence.charAt(0).toUpperCase()}${confidence.slice(1)} confidence`;
}

/** Soft status from model confidence — not a separate scored health index. */
function confidenceStatus(confidence: string | null | undefined): {
  label: string;
  className: string;
} {
  const value = (confidence ?? "").toLowerCase();
  if (value === "high") {
    return {
      label: "Sound",
      className: "bg-emerald-50 text-emerald-900 ring-emerald-200",
    };
  }
  if (value === "medium") {
    return {
      label: "Watch",
      className: "bg-amber-50 text-amber-950 ring-amber-200",
    };
  }
  if (value === "low") {
    return {
      label: "Caution",
      className: "bg-orange-50 text-orange-950 ring-orange-200",
    };
  }
  return {
    label: "Summary",
    className: "bg-surface text-ink-secondary ring-line",
  };
}

type BusinessHealthPanelProps = {
  tbId: string;
  /** Controlled expand state from the statements page (default collapsed). */
  expanded: boolean;
  onToggle: () => void;
};

export function BusinessHealthPanel({
  tbId,
  expanded,
  onToggle,
}: BusinessHealthPanelProps) {
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
        className="rounded-md border border-line bg-surface-elevated px-4 py-3"
        data-testid="business-health-loading"
      >
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-semibold text-ink">Business health</p>
          <p className="text-sm text-soft">Drafting executive summary…</p>
        </div>
      </div>
    );
  }

  if (healthQuery.error) {
    return (
      <div
        className="rounded-md border border-red-200 bg-red-50 px-4 py-3"
        data-testid="business-health-error"
      >
        <p className="text-sm font-semibold text-ink">Business health</p>
        <p className="mt-1 text-sm text-red-800">
          {healthQuery.error instanceof Error
            ? healthQuery.error.message
            : "Could not load business health summary"}
          {healthQuery.error instanceof ApiError &&
          healthQuery.error.status === 400
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
        className="rounded-md border border-line bg-surface-elevated px-4 py-3"
        id="copilot-anchor-health"
        data-testid="business-health-unavailable"
      >
        <p className="text-sm font-semibold text-ink">Business health</p>
        <p className="mt-1 text-sm text-ink-secondary">
          {data.message ??
            "Not enough history yet — upload a prior period trial balance to enable the business health summary."}
        </p>
      </div>
    );
  }

  const health = data.health;
  const points = health?.key_points?.filter((p) => p.trim()) ?? [];
  const summary = health?.summary?.trim() ?? "";
  const status = confidenceStatus(health?.confidence);

  if (!summary && points.length === 0) {
    return (
      <div
        className="rounded-md border border-line bg-surface-elevated px-4 py-3"
        id="copilot-anchor-health"
        data-testid="business-health-empty"
      >
        <p className="text-sm font-semibold text-ink">Business health</p>
        <p className="mt-1 text-sm text-ink-secondary">
          AI commentary temporarily unavailable. Statements are complete —
          refresh to retry the executive summary. Amounts are never sent to the
          model.
        </p>
      </div>
    );
  }

  const oneLiner =
    summary || points[0] || "Executive summary available — expand for detail.";

  if (!expanded) {
    return (
      <section
        className="rounded-md border border-line bg-surface-elevated px-4 py-3"
        id="copilot-anchor-health"
        data-testid="business-health-panel"
        data-expanded="false"
      >
        <div className="flex flex-wrap items-center gap-3">
          <span
            className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${status.className}`}
            data-testid="business-health-status"
          >
            {status.label}
          </span>
          <p
            className="min-w-0 flex-1 truncate text-sm text-ink"
            data-testid="business-health-summary"
            title={oneLiner}
          >
            <span className="font-semibold text-ink">Business health</span>
            <span className="text-ink-secondary"> — {oneLiner}</span>
          </p>
          <button
            type="button"
            onClick={onToggle}
            className="shrink-0 rounded-md border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-ink transition-colors hover:border-accent hover:text-accent"
            data-testid="business-health-expand"
            aria-expanded={false}
          >
            Expand
          </button>
        </div>
      </section>
    );
  }

  return (
    <section
      className="rounded-md border border-line bg-surface-elevated p-5"
      id="copilot-anchor-health"
      data-testid="business-health-panel"
      data-expanded="true"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-base font-semibold text-ink">
              Business health
            </h2>
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${status.className}`}
              data-testid="business-health-status"
            >
              {status.label}
            </span>
          </div>
          <p className="mt-1 text-sm text-ink-secondary">
            Three-bullet executive read from directional trends — gross margin,
            operating leverage, cash, and debt. No monetary amounts are sent to
            the model.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <p
            className="text-xs text-soft"
            data-testid="business-health-confidence"
          >
            {confidenceCaption(health?.confidence)}
            {health?.is_edited ? " · Edited" : " · AI draft"}
          </p>
          <button
            type="button"
            onClick={onToggle}
            className="rounded-md border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-ink transition-colors hover:border-accent hover:text-accent"
            data-testid="business-health-collapse"
            aria-expanded={true}
          >
            Collapse
          </button>
        </div>
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
