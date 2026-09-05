"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { formatDate } from "@/lib/utils";
import type {
  PerformanceExpenseShare,
  PerformanceOverviewResponse,
  PerformancePeriod,
  PerformancePeriodMetrics,
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

function GrowthBadge({ pct }: { pct: number | null }) {
  const label = formatGrowthPct(pct);
  if (label == null) {
    return (
      <span className="text-xs text-soft" data-testid="performance-kpi-growth">
        vs prior —
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
      {label} vs prior
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
}: {
  tbId: string;
  currencyCode: string;
  previewData?: PerformanceOverviewResponse;
}) {
  const { getToken } = useAuth();
  const [selectedTbId, setSelectedTbId] = useState<string>("");

  const overviewQuery = useQuery({
    queryKey: ["tb-performance-overview", tbId],
    queryFn: () =>
      apiFetch<PerformanceOverviewResponse>(
        `/trial-balances/${tbId}/performance-overview`,
        { getToken },
      ),
    enabled: previewData == null,
  });

  const data = previewData ?? overviewQuery.data;

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
        className="rounded-md border border-line bg-surface-elevated p-5"
        data-testid="performance-overview-loading"
      >
        <h2 className="font-display text-base font-semibold text-ink">
          Performance overview
        </h2>
        <p className="mt-2 text-sm text-soft">Loading period history…</p>
      </section>
    );
  }

  if (previewData == null && overviewQuery.error) {
    return (
      <section
        className="rounded-md border border-red-200 bg-red-50 p-5"
        data-testid="performance-overview-error"
      >
        <h2 className="font-display text-base font-semibold text-ink">
          Performance overview
        </h2>
        <p className="mt-2 text-sm text-red-800">
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
  const latestTbId = data.periods[data.periods.length - 1]!.tb_id;
  const isCurrentPeriod = selectedPeriod.tb_id === latestTbId;
  const multiPeriod = data.period_count > 1;

  // Newest first — same convention as Variance "Compare against".
  const periodOptions = [...data.periods].reverse();

  const trendRows: TrendRow[] = data.periods.map((period) => ({
    tbId: period.tb_id,
    label: shortPeriodLabel(period.period_end),
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

  return (
    <section
      className="space-y-5 rounded-md border border-line bg-surface-elevated p-5 sm:p-6"
      data-testid="performance-overview"
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-base font-semibold text-ink">
            Performance overview
          </h2>
          <p className="mt-1 text-sm text-ink-secondary">
            {multiPeriod
              ? `${data.period_count} periods with generated statements`
              : "Single period — upload prior trial balances to unlock trends"}
          </p>
        </div>

        {multiPeriod ? (
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
              value={selectedPeriod.tb_id}
              onChange={(event) => setSelectedTbId(event.target.value)}
              className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink shadow-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
            >
              {periodOptions.map((period) => (
                <option key={period.tb_id} value={period.tb_id}>
                  {formatDate(period.period_end)}
                  {period.tb_id === latestTbId ? " (current)" : ""}
                </option>
              ))}
            </select>
            <p
              className="text-xs text-soft"
              data-testid="performance-period-hint"
            >
              {isCurrentPeriod
                ? `Showing current period (${formatDate(selectedPeriod.period_end)}).`
                : `Showing ${formatDate(selectedPeriod.period_end)}. Trend chart always shows full history.`}
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
                <GrowthBadge pct={pct} />
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
                  ? "Full history — click a point to view that period"
                  : "Only the current period is available"}
              </p>
            </div>
            {multiPeriod ? (
              <p className="rounded-md bg-accent-muted px-2 py-1 text-xs font-medium text-accent">
                Selected {shortPeriodLabel(selectedPeriod.period_end)}
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
              data-testid="performance-expense-chart"
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
