"use client";

import { PerformanceOverview } from "@/components/statements/PerformanceOverview";
import type { PerformanceOverviewResponse } from "@/types";
import live from "./berkshire-performance.json";

/**
 * Local visual check for the performance overview using a real Berkshire
 * payload from GET /trial-balances/{id}/performance-overview.
 * Not linked from product navigation.
 */
export default function PerformancePreviewPage() {
  const data = live as PerformanceOverviewResponse;

  return (
    <main className="min-h-screen bg-surface p-6">
      <div className="mx-auto max-w-5xl space-y-4">
        <p className="text-sm text-soft">
          Dev preview — Berkshire live performance payload ({data.period_count}{" "}
          periods)
        </p>
        <PerformanceOverview
          tbId={data.tb_id}
          currencyCode={data.functional_currency}
          previewData={data}
        />
      </div>
    </main>
  );
}
