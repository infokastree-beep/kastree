"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Dot,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/currency";
import { dashboardPath } from "@/lib/copilot-navigation";
import { formatDate } from "@/lib/utils";
import type {
  PerformanceExpenseShare,
  PerformanceGranularity,
  PerformanceOverviewResponse,
  PerformancePeriod,
  PerformancePeriodMetrics,
  TrialBalanceListResponse,
} from "@/types";

const ACCENT = "#0f5c4c";
const ACCENT_MUTED = "#7aa89a";
const INK_SOFT = "#5c6b65";
const EXPENSE_COLORS = ["#0f5c4c", "#3d7a6a", "#9bbdb2"];

type KpiKey = "revenue" | "gross_profit" | "cash" | "net_profit";

const KPI_CARDS: { key: KpiKey; label: string }[] = [
  { key: "revenue", label: "Revenue" },
  { key: "gross_profit", label: "Gross profit" },
  { key: "cash", label: "Cash" },
  { key: "net_profit", label: "Net profit" },
];

const EXPENSE_LABELS: Record<PerformanceExpenseShare["code"], string> = {
  cost_of_sales: "Cost of sales",
  operating_expenses: "Operating expenses",
  depreciation: "Depreciation",
};

const GRANULARITY_OPTIONS: {
  value: PerformanceGranularity;
  label: string;
}[] = [
  { value: "monthly", label: "Monthly" },
  { value: "quarterly", label: "Quarterly" },
  { value: "yearly", label: "Yearly" },
];

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

function bucketChartLabel(period: PerformancePeriod): string {
  const key = period.bucket_key ?? period.period_end;
  if (key.includes("-Q")) {
    const [year, quarter] = key.split("-Q");
    return period.is_partial
      ? `${year} Q${quarter} (to ${shortPeriodLabel(period.period_end)})`
      : `${year} Q${quarter}`;
  }
  if (/^\d{4}$/.test(key)) {
    return period.is_partial
      ? `${key} (to ${shortPeriodLabel(period.period_end)})`
      : key;
  }
  return shortPeriodLabel(period.period_end);
}

function priorGrowthSuffix(granularity: PerformanceGranularity): string {
  if (granularity === "quarterly") return "vs prior quarter";
  if (granularity === "yearly") return "vs prior year";
  return "vs prior";
}

function toNumber(value: string | null | undefined): number | null {
  if (value == null || value === "") return null;
  const n = Number.parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

/** PoP % from consecutive statement metrics (same figures variance uses). */
function growthPct(current: number | null, prior: number | null): number | null {
  if (current == null || prior == null || prior === 0) return null;
  return ((current - prior) / Math.abs(prior)) * 100;
}

function formatGrowthPct(pct: number | null): string | null {
  if (pct == null || !Number.isFinite(pct)) return null;
  const rounded = Math.round(pct * 10) / 10;
  const sign = rounded > 0 ? "+" : "";
  return `${sign}${rounded.toFixed(1)}%`;
}

function expenseSharesFromMetrics(
  metrics: PerformancePeriodMetrics,
): PerformanceExpenseShare[] {
  const shares: PerformanceExpenseShare[] = [];
  for (const code of [
    "cost_of_sales",
    "operating_expenses",
    "depreciation",
  ] as const) {
    const raw = toNumber(metrics[code]);
    if (raw == null || raw === 0) continue;
    shares.push({
      code,
      label: EXPENSE_LABELS[code],
      amount: Math.abs(raw).toFixed(2),
    });
  }
  return shares;
}

function compactAxis(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(0)}k`;
  return String(Math.round(value));
}

function Sparkline({ values }: { values: Array<number | null> }) {
  const points = values
    .map((v, index) => (v == null ? null : { i: index, v }))
    .filter((p): p is { i: number; v: number } => p != null);

  if (points.length === 0) {
    return <div className="h-9 w-full" aria-hidden />;
  }

  const last = points[points.length - 1]?.v ?? 0;
  const first = points[0]?.v ?? last;
  const rising = last >= first;
  const stroke = points.length < 2 ? ACCENT : rising ? ACCENT : "#b91c1c";

  return (
    <div className="h-9 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
          <Area
            type="monotone"
            dataKey="v"
            stroke={stroke}
            fill={stroke}
            fillOpacity={0.12}
            strokeWidth={1.75}
            isAnimationActive={false}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function GrowthBadge({
  pct,
  priorSuffix,
}: {
  pct: number | null;
  priorSuffix: string;
}) {
  const label = formatGrowthPct(pct);
  if (label == null) {
    return (
      <span className="text-xs text-soft" data-testid="performance-kpi-growth">
        {priorSuffix} —
      </span>
    );
  }
  const positive = (pct ?? 0) > 0;
  const negative = (pct ?? 0) < 0;
  return (
    <span
      className={`text-xs font-medium tabular-nums ${
        positive ? "text-accent" : negative ? "text-red-800" : "text-soft"
      }`}
      data-testid="performance-kpi-growth"
    >
      {label} {priorSuffix}
    </span>
  );
}

type TrendRow = {
  tbId: string;
  label: string;
  revenue: number | null;
  net_profit: number | null;
  selected: boolean;
};

function PeriodDot({
  cx,
  cy,
  payload,
  fill,
  multiPeriod,
  onSelect,
}: {
  cx?: number;
  cy?: number;
  payload?: TrendRow;
  fill: string;
  multiPeriod: boolean;
  onSelect: (tbId: string) => void;
}) {
  if (cx == null || cy == null || !payload) return null;
  const selected = payload.selected;
  return (
    <Dot
      cx={cx}
      cy={cy}
      r={selected ? 5 : multiPeriod ? 3 : 4}
      fill={fill}
      stroke={selected ? "#ffffff" : fill}
      strokeWidth={selected ? 2 : 0}
      style={{ cursor: multiPeriod ? "pointer" : "default" }}
      onClick={() => onSelect(payload.tbId)}
    />
  );
}

export function PerformanceOverview({
  tbId,
  currencyCode,
  previewData,
  expanded,
  onToggle,
  collapsible = true,
}: {
  tbId: string;
  currencyCode: string;
  previewData?: PerformanceOverviewResponse;
  /** Controlled expand state from the parent (Dashboard forces open). */
  expanded: boolean;
  onToggle: () => void;
  /** When false, always show the full panel and hide expand/collapse controls. */
  collapsible?: boolean;
}) {
  const { getToken } = useAuth();
  const router = useRouter();
  const [selectedTbId, setSelectedTbId] = useState<string>("");
  const [granularity, setGranularity] =
    useState<PerformanceGranularity>("monthly");

  const overviewQuery = useQuery({
    queryKey: ["tb-performance-overview", tbId, granularity],
    queryFn: () =>
      apiFetch<PerformanceOverviewResponse>(
        `/trial-balances/${tbId}/performance-overview?granularity=${granularity}`,
        { getToken },
      ),
    enabled: previewData == null,
  });

  const data = previewData ?? overviewQuery.data;
  const activeGranularity: PerformanceGranularity =
    previewData != null ? "monthly" : (data?.granularity ?? granularity);
  const priorSuffix = priorGrowthSuffix(activeGranularity);

  // Navigation-only: full company TB list (same as Statements View period).
  // Must NOT reuse as-of-filtered overview periods — that blocks forward nav.
  const companyId = data?.company_id ?? null;
  const periodNavQuery = useQuery({
    queryKey: ["tb-period-nav", companyId],
    enabled: Boolean(companyId) && previewData == null,
    queryFn: () =>
      apiFetch<TrialBalanceListResponse>(
        `/trial-balances?company_id=${encodeURIComponent(companyId!)}&limit=100`,
        { getToken },
      ),
  });

  const navPeriodOptions = useMemo(() => {
    const items = periodNavQuery.data?.items ?? [];
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
  const companyLatestTbId = navPeriodOptions[0]?.id ?? null;
  const showNavPeriodSelect =
    previewData == null && navPeriodOptions.length > 1;

  function onNavPeriodChange(nextTbId: string) {
    if (!nextTbId || nextTbId === tbId) return;
    router.push(dashboardPath(nextTbId));
  }

  useEffect(() => {
    if (!data?.periods.length) return;
    const latestId = data.periods[data.periods.length - 1]!.tb_id;
    setSelectedTbId((current) => {
      if (current && data.periods.some((period) => period.tb_id === current)) {
        return current;
      }
      return latestId;
    });
  }, [data]);

  const selectedIndex = useMemo(() => {
    if (!data?.periods.length || !selectedTbId) return -1;
    return data.periods.findIndex((period) => period.tb_id === selectedTbId);
  }, [data, selectedTbId]);

  if (previewData == null && overviewQuery.isLoading) {
    return (
      <section
        className="rounded-md border border-line bg-surface-elevated px-4 py-3"
        id="copilot-anchor-performance"
        data-testid="performance-overview-loading"
      >
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-semibold text-ink">Performance</p>
          <p className="text-sm text-soft">Loading period history…</p>
        </div>
      </section>
    );
  }

  if (previewData == null && overviewQuery.error) {
    return (
      <section
        className="rounded-md border border-red-200 bg-red-50 px-4 py-3"
        id="copilot-anchor-performance"
        data-testid="performance-overview-error"
      >
        <p className="text-sm font-semibold text-ink">Performance</p>
        <p className="mt-1 text-sm text-red-800">
          {overviewQuery.error instanceof Error
            ? overviewQuery.error.message
            : "Could not load performance overview"}
          {overviewQuery.error instanceof ApiError &&
          overviewQuery.error.status === 404
            ? " — generate statements first."
            : null}
        </p>
      </section>
    );
  }

  if (!data || data.periods.length === 0 || selectedIndex < 0) return null;

  const selectedPeriod: PerformancePeriod = data.periods[selectedIndex]!;
  const priorPeriod: PerformancePeriod | null =
    selectedIndex > 0 ? data.periods[selectedIndex - 1]! : null;
  // Latest within the as-of series (calculation scope) — not company-wide.
  const seriesLatestTbId = data.periods[data.periods.length - 1]!.tb_id;
  const isCurrentPeriod = selectedPeriod.tb_id === seriesLatestTbId;
  const multiPeriod = data.period_count > 1;

  const trendRows: TrendRow[] = data.periods.map((period) => ({
    tbId: period.tb_id,
    label: bucketChartLabel(period),
    revenue: toNumber(period.metrics.revenue),
    net_profit: toNumber(period.metrics.net_profit),
    selected: period.tb_id === selectedPeriod.tb_id,
  }));

  const expenseShares =
    isCurrentPeriod && selectedPeriod.tb_id === data.tb_id
      ? data.expense_breakdown
      : expenseSharesFromMetrics(selectedPeriod.metrics);

  const expenseData = expenseShares.map((item) => ({
    name: item.label,
    value: Math.abs(toNumber(item.amount) ?? 0),
    code: item.code,
  }));

  const granularityToggle =
    previewData == null ? (
      <div
        className="inline-flex rounded-md border border-line bg-surface p-0.5"
        role="group"
        aria-label="Performance period granularity"
        data-testid="performance-granularity-toggle"
      >
        {GRANULARITY_OPTIONS.map((option) => {
          const active = granularity === option.value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => setGranularity(option.value)}
              className={`rounded px-2.5 py-1 text-xs font-semibold transition-colors ${
                active
                  ? "bg-accent text-accent-foreground"
                  : "text-ink-secondary hover:text-ink"
              }`}
              data-testid={`performance-granularity-${option.value}`}
              aria-pressed={active}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    ) : null;

  const periodCountLabel = (() => {
    if (activeGranularity === "quarterly") {
      const n = data.period_count;
      const sources = data.periods.reduce(
        (sum, p) => sum + (p.source_period_count ?? 1),
        0,
      );
      return `${n} quarter${n === 1 ? "" : "s"} (from ${sources} monthly statement${sources === 1 ? "" : "s"})`;
    }
    if (activeGranularity === "yearly") {
      const n = data.period_count;
      const sources = data.periods.reduce(
        (sum, p) => sum + (p.source_period_count ?? 1),
        0,
      );
      return `${n} year${n === 1 ? "" : "s"} (from ${sources} monthly statement${sources === 1 ? "" : "s"})`;
    }
    if (!multiPeriod) {
      return "Single period — upload prior trial balances to unlock trends";
    }
    return `${data.period_count} periods with generated statements`;
  })();

  if (collapsible && !expanded) {
    const priorHintParts: string[] = [];
    for (const card of KPI_CARDS) {
      const value = toNumber(selectedPeriod.metrics[card.key]);
      const priorValue = priorPeriod
        ? toNumber(priorPeriod.metrics[card.key])
        : null;
      const pct = growthPct(value, priorValue);
      const label = formatGrowthPct(pct);
      if (label && (card.key === "revenue" || card.key === "net_profit")) {
        priorHintParts.push(`${card.label} ${label}`);
      }
    }
    return (
      <section
        className="rounded-md border border-line bg-surface-elevated px-4 py-3"
        id="copilot-anchor-performance"
        data-testid="performance-overview"
        data-expanded="false"
      >
        <div className="flex flex-wrap items-center gap-3">
          <p className="shrink-0 text-sm font-semibold text-ink">Performance</p>
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-4 gap-y-2">
            {KPI_CARDS.map((card) => {
              const series = data.periods.map((p) =>
                toNumber(p.metrics[card.key]),
              );
              const value = toNumber(selectedPeriod.metrics[card.key]);
              const priorValue = priorPeriod
                ? toNumber(priorPeriod.metrics[card.key])
                : null;
              const pct = growthPct(value, priorValue);
              return (
                <div
                  key={card.key}
                  id={`copilot-anchor-performance-${card.key}`}
                  className="flex min-w-[7.5rem] items-center gap-2"
                  data-testid={`performance-kpi-${card.key}`}
                >
                  <div className="min-w-0">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-soft">
                      {card.label}
                    </p>
                    <p
                      className={`truncate text-sm font-semibold tabular-nums ${
                        value != null && value < 0 ? "text-red-800" : "text-ink"
                      }`}
                    >
                      {value == null
                        ? "—"
                        : formatCurrency(value, currencyCode)}
                    </p>
                  </div>
                  <div className="w-14 shrink-0">
                    <Sparkline values={series} />
                  </div>
                  <GrowthBadge pct={pct} priorSuffix={priorSuffix} />
                </div>
              );
            })}
          </div>
          {priorHintParts.length > 0 ? (
            <p
              className="hidden text-xs text-soft xl:block"
              data-testid="performance-collapsed-vs-prior"
            >
              {priorSuffix}: {priorHintParts.join(" · ")}
            </p>
          ) : null}
          {granularityToggle}
          <button
            type="button"
            onClick={onToggle}
            className="shrink-0 rounded-md border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-ink transition-colors hover:border-accent hover:text-accent"
            data-testid="performance-expand"
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
      className="space-y-5 rounded-md border border-line bg-surface-elevated p-5 sm:p-6"
      id="copilot-anchor-performance"
      data-testid="performance-overview"
      data-expanded="true"
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-base font-semibold text-ink">
              Performance overview
            </h2>
            {collapsible ? (
              <button
                type="button"
                onClick={onToggle}
                className="rounded-md border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-ink transition-colors hover:border-accent hover:text-accent"
                data-testid="performance-collapse"
                aria-expanded={true}
              >
                Collapse
              </button>
            ) : null}
            {granularityToggle}
          </div>
          <p className="mt-1 text-sm text-ink-secondary">{periodCountLabel}</p>
        </div>

        {showNavPeriodSelect ? (
          <div className="flex min-w-[16rem] flex-col gap-1.5">
            <label
              htmlFor="performance-period-tb"
              className="text-xs font-semibold uppercase tracking-[0.12em] text-soft"
            >
              View period
            </label>
            <select
              id="performance-period-tb"
              data-testid="performance-period-select"
              value={tbId}
              onChange={(event) => onNavPeriodChange(event.target.value)}
              className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink shadow-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
            >
              {navPeriodOptions.map((period) => (
                <option key={period.id} value={period.id}>
                  {formatDate(period.period_end)}
                  {period.id === companyLatestTbId ? " (current)" : ""}
                </option>
              ))}
            </select>
            <p
              className="text-xs text-soft"
              data-testid="performance-period-hint"
            >
              Dashboard as of {formatDate(data.period_end)}. Charts and
              aggregates use history through this date only
              {activeGranularity !== "monthly"
                ? ` (${activeGranularity} buckets).`
                : "."}
            </p>
          </div>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {KPI_CARDS.map((card) => {
          const series = data.periods.map((p) => toNumber(p.metrics[card.key]));
          const value = toNumber(selectedPeriod.metrics[card.key]);
          const priorValue = priorPeriod
            ? toNumber(priorPeriod.metrics[card.key])
            : null;
          const pct = growthPct(value, priorValue);
          return (
            <div
              key={card.key}
              id={`copilot-anchor-performance-${card.key}`}
              className="rounded-md border border-line bg-surface px-4 py-4"
              data-testid={`performance-kpi-${card.key}`}
            >
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
                {card.label}
              </p>
              <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <p
                  className={`font-display text-xl font-semibold tabular-nums tracking-tight ${
                    value != null && value < 0 ? "text-red-800" : "text-ink"
                  }`}
                >
                  {value == null
                    ? "—"
                    : formatCurrency(value, currencyCode)}
                </p>
                <GrowthBadge pct={pct} priorSuffix={priorSuffix} />
              </div>
              <div className="mt-3 border-t border-line/70 pt-2">
                <Sparkline values={series} />
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="rounded-md border border-line bg-surface p-4 sm:p-5 lg:col-span-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-ink">
                Revenue &amp; net profit
              </h3>
              <p className="mt-1 text-xs text-soft">
                {multiPeriod
                  ? activeGranularity === "monthly"
                    ? "Full history — click a point to view that period"
                    : "Aggregated history — click a point to view that bucket (growth vs prior bucket)"
                  : "Only the current period is available"}
              </p>
            </div>
            {multiPeriod ? (
              <p className="rounded-md bg-accent-muted px-2 py-1 text-xs font-medium text-accent">
                Selected {bucketChartLabel(selectedPeriod)}
              </p>
            ) : null}
          </div>
          <div
            className="mt-4 h-64 w-full"
            data-testid="performance-trend-chart"
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={trendRows}
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
                  formatter={(value: number, name: string) => [
                    formatCurrency(value, currencyCode),
                    name === "revenue" ? "Revenue" : "Net profit",
                  ]}
                  labelFormatter={(label) => String(label)}
                  contentStyle={{
                    borderRadius: 8,
                    borderColor: "#d5ded9",
                    fontSize: 12,
                  }}
                />
                <Legend
                  formatter={(value) =>
                    value === "revenue" ? "Revenue" : "Net profit"
                  }
                />
                <Line
                  type="monotone"
                  dataKey="revenue"
                  stroke={ACCENT}
                  strokeWidth={2}
                  isAnimationActive={false}
                  activeDot={{ r: 5 }}
                  dot={(props) => {
                    const payload = props.payload as TrendRow | undefined;
                    return (
                      <PeriodDot
                        key={`rev-${payload?.tbId ?? "x"}`}
                        cx={props.cx}
                        cy={props.cy}
                        payload={payload}
                        fill={ACCENT}
                        multiPeriod={multiPeriod}
                        onSelect={setSelectedTbId}
                      />
                    );
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="net_profit"
                  stroke={ACCENT_MUTED}
                  strokeWidth={2}
                  isAnimationActive={false}
                  activeDot={{ r: 5 }}
                  dot={(props) => {
                    const payload = props.payload as TrendRow | undefined;
                    return (
                      <PeriodDot
                        key={`np-${payload?.tbId ?? "x"}`}
                        cx={props.cx}
                        cy={props.cy}
                        payload={payload}
                        fill={ACCENT_MUTED}
                        multiPeriod={multiPeriod}
                        onSelect={setSelectedTbId}
                      />
                    );
                  }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-md border border-line bg-surface p-4 sm:p-5 lg:col-span-2">
          <h3 className="text-sm font-semibold text-ink">Expense mix</h3>
          <p className="mt-1 text-xs text-soft">
            Cost of sales, operating expenses, and depreciation —{" "}
            {formatDate(selectedPeriod.period_end)}
          </p>
          {expenseData.length === 0 ? (
            <p className="mt-10 text-sm text-soft">
              No expense lines available for this period.
            </p>
          ) : (
            <div
              className="mt-3 h-64 w-full"
              id="copilot-anchor-expense-mix" data-testid="performance-expense-chart"
            >
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={expenseData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={54}
                    outerRadius={86}
                    paddingAngle={2}
                    isAnimationActive={false}
                  >
                    {expenseData.map((entry, index) => (
                      <Cell
                        key={entry.code}
                        fill={EXPENSE_COLORS[index % EXPENSE_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number, name: string) => [
                      formatCurrency(value, currencyCode),
                      name,
                    ]}
                    contentStyle={{
                      borderRadius: 8,
                      borderColor: "#d5ded9",
                      fontSize: 12,
                    }}
                  />
                  <Legend
                    verticalAlign="bottom"
                    height={40}
                    wrapperStyle={{ fontSize: 12 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
