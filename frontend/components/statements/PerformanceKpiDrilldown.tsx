"use client";

/**
 * Right slide-over for a single Performance KPI.
 *
 * Data: periods already loaded by PerformanceOverview (no new fetch/math).
 * Stacking: exclusive with Copilot — opener closes Ask; Ask open closes this.
 */

import { useEffect, useId, useMemo, useRef } from "react";
import {
  CartesianGrid,
  Dot,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatCurrency } from "@/lib/currency";
import { formatDate } from "@/lib/utils";
import type { PerformancePeriod } from "@/types";

const ACCENT = "#0f5c4c";
const INK_SOFT = "#5c6b65";

export type PerformanceKpiKey =
  | "revenue"
  | "gross_profit"
  | "cash"
  | "net_profit";

export const PERFORMANCE_KPI_LABELS: Record<PerformanceKpiKey, string> = {
  revenue: "Revenue",
  gross_profit: "Gross profit",
  cash: "Cash",
  net_profit: "Net profit",
};

type DrillRow = {
  tbId: string;
  periodEnd: string;
  label: string;
  value: number | null;
  vsPriorPct: number | null;
  selected: boolean;
};

function toNumber(value: string | null | undefined): number | null {
  if (value == null || value === "") return null;
  const n = Number.parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

function growthPct(current: number | null, prior: number | null): number | null {
  if (current == null || prior == null || prior === 0) return null;
  return ((current - prior) / Math.abs(prior)) * 100;
}

function formatGrowthPct(pct: number | null): string {
  if (pct == null || !Number.isFinite(pct)) return "—";
  const rounded = Math.round(pct * 10) / 10;
  const sign = rounded > 0 ? "+" : "";
  return `${sign}${rounded.toFixed(1)}%`;
}

function shortPeriodLabel(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "2-digit",
    timeZone: "UTC",
  });
}

function compactAxis(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(0)}k`;
  return String(Math.round(value));
}

function ChartDot({
  cx,
  cy,
  payload,
  multiPeriod,
  onSelect,
}: {
  cx?: number;
  cy?: number;
  payload?: DrillRow;
  multiPeriod: boolean;
  onSelect: (tbId: string) => void;
}) {
  if (cx == null || cy == null || !payload) return null;
  const selected = payload.selected;
  return (
    <Dot
      cx={cx}
      cy={cy}
      r={selected ? 6 : multiPeriod ? 3.5 : 4}
      fill={ACCENT}
      stroke={selected ? "#ffffff" : ACCENT}
      strokeWidth={selected ? 2 : 0}
      style={{ cursor: multiPeriod ? "pointer" : "default" }}
      onClick={() => onSelect(payload.tbId)}
    />
  );
}

export function PerformanceKpiDrilldown({
  open,
  metricKey,
  periods,
  selectedTbId,
  asOfPeriodEnd,
  currencyCode,
  priorSuffix,
  onClose,
  onSelectPeriod,
  onNavigatePeriod,
}: {
  open: boolean;
  metricKey: PerformanceKpiKey;
  periods: PerformancePeriod[];
  selectedTbId: string;
  asOfPeriodEnd: string;
  currencyCode: string;
  priorSuffix: string;
  onClose: () => void;
  /** Highlight within the current as-of series (same as main Performance chart). */
  onSelectPeriod: (tbId: string) => void;
  /** Table row: navigate Dashboard View period (URL tbId) when different. */
  onNavigatePeriod: (tbId: string) => void;
}) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const label = PERFORMANCE_KPI_LABELS[metricKey];

  const rows: DrillRow[] = useMemo(() => {
    return periods.map((period, index) => {
      const value = toNumber(period.metrics[metricKey]);
      const prior =
        index > 0 ? toNumber(periods[index - 1]!.metrics[metricKey]) : null;
      return {
        tbId: period.tb_id,
        periodEnd: period.period_end,
        label: shortPeriodLabel(period.period_end),
        value,
        vsPriorPct: growthPct(value, prior),
        selected: period.tb_id === selectedTbId,
      };
    });
  }, [metricKey, periods, selectedTbId]);

  // Newest first for the table; chart keeps chronological order.
  const tableRows = useMemo(() => [...rows].reverse(), [rows]);
  const selectedRow = rows.find((r) => r.selected) ?? rows[rows.length - 1];
  const multiPeriod = rows.length > 1;

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

  if (!open) return null;

  return (
    <>
      <button
        type="button"
        aria-label={`Close ${label} detail`}
        className="fixed inset-0 z-[60] bg-ink/30 transition-opacity"
        onClick={onClose}
        data-testid="performance-kpi-drilldown-backdrop"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid="performance-kpi-drilldown"
        data-metric={metricKey}
        className="fixed inset-y-0 right-0 z-[80] flex h-full w-full max-w-none flex-col border-l border-line bg-surface-elevated shadow-xl sm:max-w-lg md:max-w-xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2
              id={titleId}
              className="font-display text-lg font-semibold text-ink"
              data-testid="performance-kpi-drilldown-title"
            >
              {label}
            </h2>
            <p className="mt-1 text-sm text-ink-secondary">
              As of {formatDate(asOfPeriodEnd)} · {currencyCode} · {rows.length}{" "}
              period{rows.length === 1 ? "" : "s"}
            </p>
            <div className="mt-3 flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <p
                className={`font-display text-2xl font-semibold tabular-nums tracking-tight ${
                  selectedRow?.value != null && selectedRow.value < 0
                    ? "text-red-800"
                    : "text-ink"
                }`}
                data-testid="performance-kpi-drilldown-value"
              >
                {selectedRow?.value == null
                  ? "—"
                  : formatCurrency(selectedRow.value, currencyCode)}
              </p>
              <span
                className="text-sm tabular-nums text-soft"
                data-testid="performance-kpi-drilldown-growth"
              >
                {formatGrowthPct(selectedRow?.vsPriorPct ?? null)} {priorSuffix}
              </span>
            </div>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-sm font-semibold text-soft transition-colors hover:bg-accent-muted hover:text-accent"
            data-testid="performance-kpi-drilldown-close"
          >
            Close
          </button>
        </header>

        <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
              History
            </p>
            {rows.length === 1 ? (
              <p className="mt-2 text-sm text-soft">
                Only one period in scope — upload prior trial balances for a
                trend.
              </p>
            ) : null}
            <div
              className="mt-3 h-[22rem] w-full"
              data-testid="performance-kpi-drilldown-chart"
            >
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={rows}
                  margin={{ top: 12, right: 16, left: 4, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#d5ded9" />
                  <XAxis
                    dataKey="label"
                    tick={{ fill: INK_SOFT, fontSize: 11 }}
                    axisLine={{ stroke: "#d5ded9" }}
                    tickLine={false}
                    minTickGap={18}
                  />
                  <YAxis
                    tickFormatter={compactAxis}
                    tick={{ fill: INK_SOFT, fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    width={52}
                  />
                  <Tooltip
                    formatter={(value: number) => [
                      formatCurrency(value, currencyCode),
                      label,
                    ]}
                    labelFormatter={(lbl) => String(lbl)}
                    contentStyle={{
                      borderRadius: 8,
                      borderColor: "#d5ded9",
                      fontSize: 12,
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke={ACCENT}
                    strokeWidth={2}
                    connectNulls={false}
                    isAnimationActive={false}
                    activeDot={{ r: 5 }}
                    dot={(props) => {
                      const payload = props.payload as DrillRow | undefined;
                      return (
                        <ChartDot
                          key={`kpi-${payload?.tbId ?? "x"}`}
                          cx={props.cx}
                          cy={props.cy}
                          payload={payload}
                          multiPeriod={multiPeriod}
                          onSelect={onSelectPeriod}
                        />
                      );
                    }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
              Periods
            </p>
            <div className="mt-2 overflow-x-auto rounded-md border border-line">
              <table
                className="min-w-full text-left text-sm"
                data-testid="performance-kpi-drilldown-table"
              >
                <thead className="bg-surface text-xs uppercase tracking-[0.08em] text-soft">
                  <tr>
                    <th className="px-3 py-2 font-semibold">Period</th>
                    <th className="px-3 py-2 text-right font-semibold">
                      Amount
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
                      vs prior
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((row) => {
                    const selected = row.selected;
                    return (
                      <tr
                        key={row.tbId}
                        data-testid={`performance-kpi-drilldown-row-${row.tbId}`}
                        data-selected={selected ? "true" : "false"}
                        className={`cursor-pointer border-t border-line/80 transition-colors ${
                          selected ? "bg-accent-muted/40" : "hover:bg-surface"
                        }`}
                        onClick={() => {
                          onSelectPeriod(row.tbId);
                          onNavigatePeriod(row.tbId);
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            onSelectPeriod(row.tbId);
                            onNavigatePeriod(row.tbId);
                          }
                        }}
                        tabIndex={0}
                        role="button"
                        aria-label={`View ${label} for ${formatDate(row.periodEnd)}`}
                      >
                        <td className="px-3 py-2.5 font-medium text-ink">
                          {formatDate(row.periodEnd)}
                          {selected ? (
                            <span className="ml-2 text-xs font-semibold text-accent">
                              Selected
                            </span>
                          ) : null}
                        </td>
                        <td
                          className={`px-3 py-2.5 text-right tabular-nums ${
                            row.value != null && row.value < 0
                              ? "text-red-800"
                              : "text-ink"
                          }`}
                        >
                          {row.value == null
                            ? "—"
                            : formatCurrency(row.value, currencyCode)}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-soft">
                          {formatGrowthPct(row.vsPriorPct)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
