"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { formatCurrency, formatCurrencyCode } from "@/lib/currency";
import { DISCLAIMER_TEXT } from "@/lib/constants";
import type { StatementBlock, StatementLine, StatementsResponse } from "@/types";
import { BusinessHealthPanel } from "./BusinessHealthPanel";
import { ExportButton } from "./ExportButton";
import { MaterialitySuggestionBanner } from "./MaterialitySuggestionBanner";
import { PerformanceOverview } from "./PerformanceOverview";
import { RiskFlagsPanel } from "./RiskFlagsPanel";
import { CopilotPanel, type CopilotNavigateTarget } from "./CopilotPanel";
import { VariancePanel } from "./VariancePanel";

type Tab = "SOPL" | "SOFP" | "SOCIE" | "Variance" | "Risk";

const STATEMENT_TABS: Tab[] = ["SOPL", "SOFP", "SOCIE"];
const ALL_TABS: Tab[] = ["SOPL", "SOFP", "SOCIE", "Variance", "Risk"];

/** Grand-total face lines — stronger weight than intermediate subtotals. */
function isGrandTotal(line: StatementLine): boolean {
  const code = line.line_item_code;
  return (
    code.startsWith("total_") ||
    code === "net_profit" ||
    code === "total_equity_closing"
  );
}

/**
 * Assign a section index that increments after each subtotal so detail
 * groups can alternate subtle shading (financial-statement convention).
 */
function sectionIndexes(lines: StatementLine[]): number[] {
  let section = 0;
  return lines.map((line) => {
    const current = section;
    if (line.is_subtotal) {
      section += 1;
    }
    return current;
  });
}

function StatementTable({
  block,
  currencyCode,
}: {
  block: StatementBlock;
  currencyCode: string;
}) {
  const sections = sectionIndexes(block.lines);

  return (
    <div className="overflow-x-auto rounded-md border border-line bg-surface-elevated">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-line bg-accent-muted/50 text-xs uppercase tracking-[0.12em] text-soft">
          <tr>
            <th className="px-4 py-3 font-semibold">Line item</th>
            <th className="px-4 py-3 text-right font-semibold">Amount</th>
          </tr>
        </thead>
        <tbody>
          {block.lines.map((line, index) => {
            const numericAmount = Number.parseFloat(line.amount);
            const isNegative =
              Number.isFinite(numericAmount) && numericAmount < 0;
            const grandTotal = line.is_subtotal && isGrandTotal(line);
            const section = sections[index] ?? 0;
            const sectionShade =
              !line.is_subtotal && section % 2 === 1
                ? "bg-accent-muted/35"
                : !line.is_subtotal
                  ? "bg-surface-elevated"
                  : "";

            let rowClass = "border-b border-line/70";
            if (grandTotal) {
              rowClass += " border-t-2 border-t-line-strong bg-accent-muted";
            } else if (line.is_subtotal) {
              rowClass += " bg-[#eef3f1]";
            } else {
              rowClass += ` ${sectionShade}`;
            }

            const nameWeight = grandTotal
              ? "font-bold text-ink"
              : line.is_subtotal
                ? "font-semibold text-ink"
                : "font-normal text-ink-secondary";

            const amountWeight = grandTotal
              ? "font-bold text-ink"
              : line.is_subtotal
                ? "font-semibold text-ink"
                : "font-normal text-ink";

            return (
              <tr key={line.id} className={rowClass}>
                <td
                  className={`py-2.5 ${nameWeight} ${
                    line.is_subtotal ? "pl-4 pr-4" : "pl-10 pr-4 sm:pl-12"
                  }`}
                >
                  {line.line_item_name}
                </td>
                <td
                  className={`px-4 py-2.5 text-right tabular-nums ${amountWeight} ${
                    isNegative ? "text-red-800" : ""
                  }`}
                >
                  {formatCurrency(line.amount, currencyCode)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function StatementsDashboard({ tbId }: { tbId: string }) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("SOPL");
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [healthExpanded, setHealthExpanded] = useState(false);
  const [performanceExpanded, setPerformanceExpanded] = useState(false);

  const statementsQuery = useQuery({
    queryKey: ["tb-statements", tbId],
    queryFn: async () => {
      try {
        return await apiFetch<StatementsResponse>(
          `/trial-balances/${tbId}/statements`,
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
      apiFetch<StatementsResponse>(`/trial-balances/${tbId}/statements`, {
        method: "POST",
        getToken,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["tb-statements", tbId], data);
      void queryClient.invalidateQueries({ queryKey: ["tb-variance", tbId] });
      void queryClient.invalidateQueries({ queryKey: ["tb-risk", tbId] });
      void queryClient.invalidateQueries({
        queryKey: ["tb-business-health", tbId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["tb-performance-overview", tbId],
      });
    },
  });

  const statementsData = statementsQuery.data ?? generateMutation.data ?? null;
  const currencyCode = statementsData?.functional_currency ?? "GBP";
  const isStatementTab = STATEMENT_TABS.includes(tab);

  const block = isStatementTab
    ? statementsData?.statements.find((s) => s.statement_type === tab)
    : undefined;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-display text-heading-lg text-ink">Statements</h1>
          <p className="mt-1 text-sm text-ink-secondary">
            {statementsData ? (
              <>
                Period ending{" "}
                <span className="font-medium text-ink">
                  {statementsData.period_end}
                </span>
                {" · "}
                <span className="font-mono font-medium text-ink">
                  {formatCurrencyCode(currencyCode)}
                </span>
              </>
            ) : (
              "Review SOPL, SOFP, SOCIE, variance, and risk flags for this trial balance."
            )}
          </p>
        </div>
        {statementsData ? (
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setCopilotOpen(true)}
              className="flex items-center gap-1.5 rounded-md border border-line bg-surface-elevated px-3 py-1.5 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent"
              data-testid="copilot-ask-button"
            >
              Ask
            </button>
            <ExportButton tbId={tbId} />
            <button
              type="button"
              disabled={generateMutation.isPending}
              onClick={() => generateMutation.mutate()}
              className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
            >
              {generateMutation.isPending
                ? "Regenerating…"
                : "Regenerate Statements"}
            </button>
          </div>
        ) : null}
      </div>

      {generateMutation.error && statementsData ? (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {generateMutation.error instanceof Error
            ? generateMutation.error.message
            : "Regenerate failed"}
        </p>
      ) : null}

      <p className="rounded-md border border-amber-200/80 bg-amber-50/90 px-3 py-2 text-xs text-amber-950 sm:text-sm">
        <span className="font-semibold">Disclaimer: </span>
        {DISCLAIMER_TEXT}
      </p>

      {statementsQuery.isLoading ? (
        <p className="text-sm text-soft">Loading statements…</p>
      ) : null}

      {statementsQuery.error ? (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {statementsQuery.error instanceof Error
            ? statementsQuery.error.message
            : "Failed to load statements"}
        </p>
      ) : null}

      {!statementsQuery.isLoading && statementsQuery.data === null ? (
        <div className="space-y-4 rounded-md border border-line bg-surface-elevated p-6">
          <p className="text-sm text-ink-secondary">
            Statements have not been generated yet for this trial balance.
          </p>
          {generateMutation.error ? (
            <div className="space-y-2 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
              <p>
                {generateMutation.error instanceof Error
                  ? generateMutation.error.message
                  : "Generate failed"}
              </p>
              {generateMutation.error instanceof ApiError &&
              generateMutation.error.message
                .toLowerCase()
                .includes("confirm mapping") ? (
                <p>
                  <Link
                    href={`/mapping/${tbId}`}
                    className="font-medium underline"
                  >
                    Go to mapping review
                  </Link>
                </p>
              ) : null}
            </div>
          ) : null}
          <button
            type="button"
            disabled={generateMutation.isPending}
            onClick={() => generateMutation.mutate()}
            className="rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover disabled:opacity-50"
          >
            {generateMutation.isPending
              ? "Generating…"
              : "Generate Statements"}
          </button>
        </div>
      ) : null}

      {statementsData ? (
        <>
          <MaterialitySuggestionBanner
            tbId={tbId}
            currencyCode={currencyCode}
          />

          <div
            className="space-y-2"
            data-testid="context-strips"
          >
            <BusinessHealthPanel
              tbId={tbId}
              expanded={healthExpanded}
              onToggle={() => setHealthExpanded((v) => !v)}
            />
            <PerformanceOverview
              tbId={tbId}
              currencyCode={currencyCode}
              expanded={performanceExpanded}
              onToggle={() => setPerformanceExpanded((v) => !v)}
            />
          </div>

          <div
            className="space-y-4"
            data-testid="statements-primary-workspace"
          >
            {isStatementTab ? (
              <p className="text-sm text-ink-secondary">
                All amounts in{" "}
                <span className="font-mono font-medium text-ink">
                  {formatCurrencyCode(currencyCode)}
                </span>
              </p>
            ) : null}

            <div
              className="sticky top-0 z-20 -mx-1 border-b border-line bg-surface/95 px-1 backdrop-blur supports-[backdrop-filter]:bg-surface/80"
              data-testid="statements-tab-bar"
            >
              <div className="flex flex-wrap gap-1">
                {ALL_TABS.map((name) => (
                  <button
                    key={name}
                    type="button"
                    onClick={() => setTab(name)}
                    className={`px-3 py-2.5 text-sm font-semibold transition-colors ${
                      tab === name
                        ? "border-b-2 border-accent text-accent"
                        : "text-soft hover:text-ink"
                    }`}
                  >
                    {name}
                  </button>
                ))}
              </div>
            </div>

            {tab === "Variance" ? (
              <VariancePanel
                tbId={tbId}
                currencyCode={currencyCode}
                companyId={statementsData.company_id}
                periodEnd={statementsData.period_end}
              />
            ) : null}
            {tab === "Risk" ? <RiskFlagsPanel tbId={tbId} /> : null}
            {isStatementTab ? (
              block ? (
                <StatementTable block={block} currencyCode={currencyCode} />
              ) : (
                <p className="text-sm text-soft">No {tab} lines returned.</p>
              )
            ) : null}
          </div>
        </>
      ) : null}

      <CopilotPanel
        tbId={tbId}
        open={copilotOpen}
        onClose={() => setCopilotOpen(false)}
        onNavigateCitation={(target: CopilotNavigateTarget) => {
          if (target.contextStrip === "health") {
            setHealthExpanded(true);
          }
          if (target.contextStrip === "performance") {
            setPerformanceExpanded(true);
          }
          if (target.tab) {
            setTab(target.tab);
          }
          const delay =
            target.contextStrip || target.tab ? 120 : 0;
          window.setTimeout(() => {
            const el = document.getElementById(target.anchorId);
            if (!el) return;
            el.scrollIntoView({ behavior: "smooth", block: "center" });
            el.classList.remove("copilot-cite-flash");
            // Force reflow so re-clicking the same chip retriggers the flash.
            void el.offsetWidth;
            el.classList.add("copilot-cite-flash");
          }, delay);
        }}
      />
    </div>
  );

}
