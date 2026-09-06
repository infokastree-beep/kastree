"use client";

/**
 * Dashboard page body — Business Health + Performance, always expanded.
 * Ask lives in TbWorkspaceProvider (shared layout); citations scroll here.
 */

import { BusinessHealthPanel } from "./BusinessHealthPanel";
import { PerformanceOverview } from "./PerformanceOverview";
import { useTbWorkspace } from "./TbWorkspaceProvider";

export function DashboardOverview({
  currencyCode = "GBP",
}: {
  currencyCode?: string;
}) {
  const { tbId, openAsk } = useTbWorkspace();

  return (
    <div className="space-y-5" data-testid="dashboard-overview">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-display text-heading-lg text-ink">Dashboard</h1>
          <p className="mt-1 text-sm text-ink-secondary">
            Business health and performance for this trial balance — the
            analytics surface that grows with new metrics and charts.
          </p>
        </div>
        <button
          type="button"
          onClick={openAsk}
          className="flex items-center gap-1.5 rounded-md border border-line bg-surface-elevated px-3 py-1.5 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent"
          data-testid="copilot-ask-button"
        >
          Ask
        </button>
      </div>

      <div className="space-y-4" data-testid="dashboard-analytics">
        <BusinessHealthPanel
          tbId={tbId}
          expanded
          onToggle={() => undefined}
          collapsible={false}
        />
        <PerformanceOverview
          tbId={tbId}
          currencyCode={currencyCode}
          expanded
          onToggle={() => undefined}
          collapsible={false}
        />
      </div>
    </div>
  );
}
