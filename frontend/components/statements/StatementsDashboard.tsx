"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { formatCurrency, formatCurrencyCode } from "@/lib/currency";
import { DISCLAIMER_TEXT } from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import { statementsPath, parseStatementsTab } from "@/lib/copilot-navigation";
import type {
  StatementBlock,
  StatementLine,
  StatementsResponse,
  TrialBalanceListResponse,
  ValidationResponse,
} from "@/types";
import { ExportButton } from "./ExportButton";
import { MaterialitySuggestionBanner } from "./MaterialitySuggestionBanner";
import { RiskFlagsPanel } from "./RiskFlagsPanel";
import { StatementLineDrilldown } from "./StatementLineDrilldown";
import { VariancePanel } from "./VariancePanel";
import { useTbWorkspace } from "./TbWorkspaceProvider";

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
  periodEnd,
  priorPeriodEnd,
  selectedLineId,
  onSelectLine,
}: {
  block: StatementBlock;
  currencyCode: string;
  periodEnd: string;
  priorPeriodEnd?: string | null;
  selectedLineId: string | null;
  onSelectLine: (line: StatementLine) => void;
}) {
  const sections = sectionIndexes(block.lines);
  const comparative = Boolean(priorPeriodEnd);

  function renderAmount(value: string | null | undefined): {
    text: string;
    isNegative: boolean;
    isEmpty: boolean;
  } {
    if (value == null || value === "") {
      return { text: "—", isNegative: false, isEmpty: true };
    }
    const numericAmount = Number.parseFloat(value);
    const isNegative = Number.isFinite(numericAmount) && numericAmount < 0;
    return {
      text: formatCurrency(value, currencyCode),
      isNegative,
      isEmpty: false,
    };
  }

  return (
    <div className="overflow-x-auto rounded-md border border-line bg-surface-elevated">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-line bg-accent-muted/50 text-xs uppercase tracking-[0.12em] text-soft">
          <tr>
            <th className="px-4 py-3 font-semibold">Line item</th>
            <th className="px-4 py-3 text-right font-semibold">
              {formatDate(periodEnd)}
            </th>
            {comparative ? (
              <th className="px-4 py-3 text-right font-semibold">
                {formatDate(priorPeriodEnd!)}
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {block.lines.map((line, index) => {
            const current = renderAmount(line.amount);
            const prior = comparative
              ? renderAmount(line.prior_amount)
              : null;
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

            const selected = selectedLineId === line.id;
            const interactiveClass = selected
              ? " cursor-pointer ring-1 ring-inset ring-accent/40"
              : " cursor-pointer hover:bg-accent-muted/50";

            return (
              <tr
                key={line.id}
                className={`${rowClass}${interactiveClass}`}
                data-line-code={line.line_item_code}
                data-testid={`stmt-row-${line.line_item_code}`}
                tabIndex={0}
                aria-label={`View sources for ${line.line_item_name}`}
                onClick={() => onSelectLine(line)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectLine(line);
                  }
                }}
              >
                <td
                  className={`py-2.5 ${nameWeight} ${
                    line.is_subtotal ? "pl-4 pr-4" : "pl-10 pr-4 sm:pl-12"
                  }`}
                >
                  {line.line_item_name}
                </td>
                <td
                  className={`px-4 py-2.5 text-right tabular-nums ${amountWeight} ${
                    current.isEmpty
                      ? "text-soft"
                      : current.isNegative
                        ? "text-red-800"
                        : ""
                  }`}
                  data-testid={`stmt-amount-current-${line.line_item_code}`}
                >
                  {current.text}
                </td>
                {prior ? (
                  <td
                    className={`px-4 py-2.5 text-right tabular-nums ${amountWeight} ${
                      prior.isEmpty
                        ? "text-soft"
                        : prior.isNegative
                          ? "text-red-800"
                          : ""
                    }`}
                    data-testid={`stmt-amount-prior-${line.line_item_code}`}
                  >
                    {prior.text}
                  </td>
                ) : null}
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
  const router = useRouter();
  const searchParams = useSearchParams();
  const { openAsk, closeAsk, askOpen } = useTbWorkspace();
  const initialTab = parseStatementsTab(searchParams?.get("tab")) ?? "SOPL";
  const [tab, setTab] = useState<Tab>(initialTab);
  const [drilldownLineId, setDrilldownLineId] = useState<string | null>(null);

  // Stacking rule: exclusive with Copilot — never two right sheets at once.
  useEffect(() => {
    if (askOpen && drilldownLineId != null) {
      setDrilldownLineId(null);
    }
  }, [askOpen, drilldownLineId]);

  function openLineDrilldown(line: StatementLine) {
    closeAsk();
    setDrilldownLineId(line.id);
  }

  function closeLineDrilldown() {
    setDrilldownLineId(null);
  }

  useEffect(() => {
    const fromUrl = parseStatementsTab(searchParams?.get("tab"));
    if (fromUrl) setTab(fromUrl);
  }, [searchParams]);

  useEffect(() => {
    function onSetTab(event: Event) {
      const detail = (event as CustomEvent<{ tab?: string }>).detail;
      const next = parseStatementsTab(detail?.tab);
      if (next) setTab(next);
    }
    window.addEventListener("kastree:set-statements-tab", onSetTab);
    return () =>
      window.removeEventListener("kastree:set-statements-tab", onSetTab);
  }, []);

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
      void queryClient.invalidateQueries({
        queryKey: ["tb-period-nav"],
      });
    },
  });

  const statementsData = statementsQuery.data ?? generateMutation.data ?? null;

  const validationQuery = useQuery({
    queryKey: ["tb-validation", tbId],
    enabled: !statementsQuery.isLoading && statementsQuery.data === null,
    queryFn: async () => {
      try {
        return await apiFetch<ValidationResponse>(
          `/trial-balances/${tbId}/validation`,
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

  const blockingFailures = useMemo(() => {
    const checks = validationQuery.data?.checks ?? [];
    return checks.filter(
      (check) =>
        !check.passed &&
        check.severity === "error" &&
        (check.check_name === "tb_integrity" ||
          check.check_name === "balance_sheet_balance" ||
          check.check_name === "net_assets"),
    );
  }, [validationQuery.data?.checks]);

  const currencyCode = statementsData?.functional_currency ?? "GBP";
  const isStatementTab = STATEMENT_TABS.includes(tab);
  const block = isStatementTab
    ? statementsData?.statements.find((s) => s.statement_type === tab)
    : undefined;

  // Full company period list for View period navigation (not as-of-filtered
  // performance history). Filtering to ≤ current period is correct for prior
  // comparison / chart "as of", but reused here it creates a forward dead-end.
  const companyId = statementsData?.company_id ?? null;
  const periodNavQuery = useQuery({
    queryKey: ["tb-period-nav", companyId],
    enabled: Boolean(companyId),
    queryFn: () =>
      apiFetch<TrialBalanceListResponse>(
        `/trial-balances?company_id=${encodeURIComponent(companyId!)}&limit=100`,
        { getToken },
      ),
  });

  const periodOptions = useMemo(() => {
    const items = periodNavQuery.data?.items ?? [];
    // Statements-ready statuses (same routing family as client TB links).
    const navigable = items.filter(
      (tb) =>
        tb.id === tbId ||
        tb.status === "complete" ||
        tb.status === "validating" ||
        tb.status === "generating" ||
        tb.status === "analysing",
    );
    return [...navigable].sort((a, b) => {
      if (a.period_end !== b.period_end) {
        return a.period_end < b.period_end ? 1 : -1;
      }
      return a.id < b.id ? 1 : -1;
    });
  }, [periodNavQuery.data?.items, tbId]);
  const multiPeriod = periodOptions.length > 1;
  // Company-wide newest — not "newest among as-of-filtered priors".
  const latestTbId = periodOptions[0]?.id ?? null;

  function onPeriodChange(nextTbId: string) {
    if (!nextTbId || nextTbId === tbId) return;
    const params = new URLSearchParams();
    if (tab !== "SOPL") params.set("tab", tab);
    const qs = params.toString();
    router.push(qs ? `${statementsPath(nextTbId)}?${qs}` : statementsPath(nextTbId));
  }

  return (
    <div className="space-y-5" data-testid="statements-workspace">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-display text-heading-lg text-ink">Statements</h1>
          <p className="mt-1 text-sm text-ink-secondary">
            {statementsData ? (
              <>
                Period ending{" "}
                <span className="font-medium text-ink">
                  {formatDate(statementsData.period_end)}
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
        <div className="flex flex-wrap items-end gap-3">
          {multiPeriod ? (
            <div className="flex min-w-[14rem] flex-col gap-1.5">
              <label
                htmlFor="statements-period-tb"
                className="text-xs font-semibold uppercase tracking-[0.12em] text-soft"
              >
                View period
              </label>
              <select
                id="statements-period-tb"
                data-testid="statements-period-select"
                value={tbId}
                onChange={(event) => onPeriodChange(event.target.value)}
                className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink shadow-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              >
                {periodOptions.map((period) => (
                  <option key={period.id} value={period.id}>
                    {formatDate(period.period_end)}
                    {period.id === latestTbId ? " (current)" : ""}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          {statementsData ? (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={openAsk}
                className="flex items-center gap-1.5 rounded-md border border-line bg-surface-elevated px-3 py-1.5 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent"
                data-testid="copilot-ask-button"
              >
                Ask Copilot
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

      {statementsData?.mappings_stale ? (
        <div
          className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-300 bg-amber-50 px-4 py-3"
          data-testid="stale-mapping-banner"
          role="status"
        >
          <p className="text-sm text-amber-950">
            <span className="font-semibold">Mappings have changed</span> since
            these statements were generated. Figures may be out of date —
            regenerate to refresh from the current mapping.
          </p>
          <button
            type="button"
            disabled={generateMutation.isPending}
            onClick={() => generateMutation.mutate()}
            className="shrink-0 rounded-md bg-accent px-3 py-2 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover disabled:opacity-50"
            data-testid="stale-mapping-regenerate"
          >
            {generateMutation.isPending
              ? "Regenerating…"
              : "Regenerate Statements"}
          </button>
        </div>
      ) : null}

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
          {blockingFailures.length > 0 ? (
            <div
              className="space-y-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950"
              data-testid="statements-blocking-validation"
            >
              <p className="font-semibold">
                Blocking validation checks have not passed
              </p>
              <ul className="list-disc space-y-1 pl-5">
                {blockingFailures.map((check) => (
                  <li key={check.check_name}>{check.message}</li>
                ))}
              </ul>
              <p>
                <Link
                  href={`/mapping/${tbId}`}
                  className="font-medium underline"
                >
                  Review mapping
                </Link>
                {" — then confirm again to re-run validation."}
              </p>
            </div>
          ) : null}
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
            disabled={
              generateMutation.isPending ||
              (validationQuery.data != null &&
                !validationQuery.data.can_generate_statements)
            }
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
                <StatementTable
                  block={block}
                  currencyCode={currencyCode}
                  periodEnd={statementsData.period_end}
                  priorPeriodEnd={statementsData.prior_period_end}
                  selectedLineId={drilldownLineId}
                  onSelectLine={openLineDrilldown}
                />
              ) : (
                <p className="text-sm text-soft">No {tab} lines returned.</p>
              )
            ) : null}
          </div>

          <StatementLineDrilldown
            open={drilldownLineId != null}
            tbId={tbId}
            lineId={drilldownLineId}
            onClose={closeLineDrilldown}
          />
        </>
      ) : null}
    </div>
  );
}
