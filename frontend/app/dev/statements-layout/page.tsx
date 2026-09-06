"use client";

/**
 * Dev harness for Option B statements layout (collapsed context strips).
 * No auth — Berkshire performance preview JSON + mock health strip.
 * Not linked from product navigation.
 */

import { useMemo, useState } from "react";
import { PerformanceOverview } from "@/components/statements/PerformanceOverview";
import type { PerformanceOverviewResponse } from "@/types";
import live from "../performance-preview/berkshire-performance.json";

function MockBusinessHealthStrip({
  expanded,
  onToggle,
}: {
  expanded: boolean;
  onToggle: () => void;
}) {
  const summary =
    "Trading remains solid with improving cash cover and stable operating leverage.";
  const points = [
    "Gross margin trend is improving versus the prior period.",
    "Operating expense growth is broadly in line with revenue.",
    "Cash position is strengthening on the period.",
  ];

  if (!expanded) {
    return (
      <section
        className="rounded-md border border-line bg-surface-elevated px-4 py-3"
        id="copilot-anchor-health"
        data-testid="business-health-panel"
        data-expanded="false"
      >
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex shrink-0 items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-900 ring-1 ring-inset ring-emerald-200">
            Sound
          </span>
          <p
            className="min-w-0 flex-1 truncate text-sm text-ink"
            data-testid="business-health-summary"
          >
            <span className="font-semibold">Business health</span>
            <span className="text-ink-secondary"> — {summary}</span>
          </p>
          <button
            type="button"
            onClick={onToggle}
            className="shrink-0 rounded-md border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-ink"
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
        <h2 className="font-display text-base font-semibold text-ink">
          Business health
        </h2>
        <button
          type="button"
          onClick={onToggle}
          className="rounded-md border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-ink"
          data-testid="business-health-collapse"
          aria-expanded={true}
        >
          Collapse
        </button>
      </div>
      <p className="mt-4 text-sm text-ink" data-testid="business-health-summary">
        {summary}
      </p>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-ink-secondary">
        {points.map((point) => (
          <li key={point}>{point}</li>
        ))}
      </ol>
    </section>
  );
}

export default function StatementsLayoutPreviewPage() {
  const data = live as PerformanceOverviewResponse;
  const [healthExpanded, setHealthExpanded] = useState(false);
  const [performanceExpanded, setPerformanceExpanded] = useState(false);

  const statementRows = useMemo(
    () => [
      { name: "Revenue", amount: "12,450,000" },
      { name: "Cost of sales", amount: "(7,210,000)" },
      { name: "Gross profit", amount: "5,240,000", bold: true },
      { name: "Operating expenses", amount: "(3,180,000)" },
      { name: "Operating profit", amount: "2,060,000", bold: true },
      { name: "Net profit", amount: "1,640,000", bold: true },
    ],
    [],
  );

  return (
    <main className="min-h-screen bg-surface p-6">
      <div className="mx-auto max-w-5xl space-y-5">
        <p className="text-sm text-soft" data-testid="layout-harness-label">
          Dev layout harness — Option B (collapsed context strips). No auth.
        </p>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-heading-lg text-ink">Statements</h1>
            <p className="mt-1 text-sm text-ink-secondary">
              Period ending{" "}
              <span className="font-medium text-ink">2026-09-20</span>
              {" · "}
              <span className="font-mono font-medium text-ink">USD</span>
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-md border border-line bg-surface-elevated px-3 py-1.5 text-sm font-semibold"
              data-testid="copilot-ask-button"
            >
              Ask
            </button>
            <button
              type="button"
              className="rounded-md border border-line bg-surface-elevated px-3 py-1.5 text-sm font-semibold"
            >
              Export
            </button>
          </div>
        </div>

        <p className="rounded-md border border-amber-200/80 bg-amber-50/90 px-3 py-2 text-xs text-amber-950">
          <span className="font-semibold">Disclaimer: </span>
          Draft management accounts — review before relying on them.
        </p>

        {/* Materiality intentionally omitted — nothing actionable */}
        <div data-testid="materiality-absent-marker" className="hidden" />

        <div className="space-y-2" data-testid="context-strips">
          <MockBusinessHealthStrip
            expanded={healthExpanded}
            onToggle={() => setHealthExpanded((v) => !v)}
          />
          <PerformanceOverview
            tbId={data.tb_id}
            currencyCode={data.functional_currency}
            previewData={data}
            expanded={performanceExpanded}
            onToggle={() => setPerformanceExpanded((v) => !v)}
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-md border border-line px-2.5 py-1 text-xs font-semibold"
            data-testid="simulate-health-citation"
            onClick={() => {
              setHealthExpanded(true);
              window.setTimeout(() => {
                document
                  .getElementById("copilot-anchor-health")
                  ?.scrollIntoView({ behavior: "smooth", block: "center" });
              }, 50);
            }}
          >
            Simulate health citation
          </button>
          <button
            type="button"
            className="rounded-md border border-line px-2.5 py-1 text-xs font-semibold"
            data-testid="simulate-performance-citation"
            onClick={() => {
              setPerformanceExpanded(true);
              window.setTimeout(() => {
                document
                  .getElementById("copilot-anchor-performance")
                  ?.scrollIntoView({ behavior: "smooth", block: "center" });
              }, 50);
            }}
          >
            Simulate performance citation
          </button>
        </div>

        <div data-testid="statements-primary-workspace" className="space-y-4">
          <div
            className="sticky top-0 z-20 border-b border-line bg-surface/95 backdrop-blur"
            data-testid="statements-tab-bar"
          >
            <div className="flex flex-wrap gap-1">
              {["SOPL", "SOFP", "SOCIE", "Variance", "Risk"].map((name, i) => (
                <button
                  key={name}
                  type="button"
                  className={`px-3 py-2.5 text-sm font-semibold ${
                    i === 0
                      ? "border-b-2 border-accent text-accent"
                      : "text-soft"
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>
          </div>

          <div
            className="overflow-x-auto rounded-md border border-line bg-surface-elevated"
            data-testid="sopl-table"
          >
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-line text-xs uppercase tracking-[0.12em] text-soft">
                <tr>
                  <th className="px-4 py-3">Line item</th>
                  <th className="px-4 py-3 text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {statementRows.map((row) => (
                  <tr key={row.name} className="border-b border-line/70">
                    <td
                      className={`px-4 py-2.5 ${
                        row.bold
                          ? "font-semibold text-ink"
                          : "text-ink-secondary"
                      }`}
                    >
                      {row.name}
                    </td>
                    <td className="px-4 py-2.5 text-right font-medium tabular-nums text-ink">
                      {row.amount}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </main>
  );
}
