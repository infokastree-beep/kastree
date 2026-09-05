"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
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
import type { PerformanceOverviewResponse } from "@/types";

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

function Sparkline({ values }: { values: Array<number | null> }) {
  const points = values
    .map((v, index) => (v == null ? null : { i: index, v }))
    .filter((p): p is { i: number; v: number } => p != null);

  if (points.length === 0) {
    return <div className="h-10 w-full" aria-hidden />;
  }

  const last = points[points.length - 1]?.v ?? 0;
  const first = points[0]?.v ?? last;
  const rising = last >= first;
  const stroke = points.length < 2 ? ACCENT : rising ? ACCENT : "#b91c1c";

  return (
    <div className="h-10 w-full">
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

function compactAxis(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(0)}k`;
  return String(Math.round(value));
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

  const overviewQuery = useQuery({
    queryKey: ["tb-performance-overview", tbId],
    queryFn: () =>
      apiFetch<PerformanceOverviewResponse>(
        `/trial-balances/${tbId}/performance-overview`,
        { getToken },
      ),
    enabled: previewData == null,
  });

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

  const data = previewData ?? overviewQuery.data;
  if (!data || data.periods.length === 0) return null;

  const current = data.periods[data.periods.length - 1]!;
  const multiPeriod = data.period_count > 1;

  const trendRows = data.periods.map((period) => ({
    label: shortPeriodLabel(period.period_end),
    revenue: toNumber(period.metrics.revenue),
    net_profit: toNumber(period.metrics.net_profit),
  }));

  const expenseData = data.expense_breakdown.map((item) => ({
    name: item.label,
    value: Math.abs(toNumber(item.amount) ?? 0),
    code: item.code,
  }));

  return (
    <section
      className="space-y-4 rounded-md border border-line bg-surface-elevated p-5"
      data-testid="performance-overview"
    >
      <div>
        <h2 className="font-display text-base font-semibold text-ink">
          Performance overview
        </h2>
        <p className="mt-1 text-sm text-ink-secondary">
          {multiPeriod
            ? `${data.period_count} periods with generated statements`
            : "Single period — upload prior trial balances to unlock trends"}
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {KPI_CARDS.map((card) => {
          const series = data.periods.map((p) => toNumber(p.metrics[card.key]));
          const latest = toNumber(current.metrics[card.key]);
          return (
            <div
              key={card.key}
              className="rounded-md border border-line/80 bg-surface px-3 py-3"
              data-testid={`performance-kpi-${card.key}`}
            >
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
                {card.label}
              </p>
              <p
                className={`mt-1 font-display text-lg font-semibold tabular-nums ${
                  latest != null && latest < 0 ? "text-red-800" : "text-ink"
                }`}
              >
                {latest == null ? "—" : formatCurrency(String(latest), currencyCode)}
              </p>
              <Sparkline values={series} />
            </div>
          );
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="rounded-md border border-line/80 bg-surface p-4 lg:col-span-3">
          <h3 className="text-sm font-semibold text-ink">
            Revenue &amp; net profit
          </h3>
          <p className="mt-1 text-xs text-soft">
            {multiPeriod
              ? "Across all available statement periods for this company"
              : "Only the current period is available"}
          </p>
          <div className="mt-3 h-56 w-full" data-testid="performance-trend-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={trendRows}
                margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#d5ded9" />
                <XAxis
                  dataKey="label"
                  tick={{ fill: INK_SOFT, fontSize: 11 }}
                  axisLine={{ stroke: "#d5ded9" }}
                  tickLine={false}
                />
                <YAxis
                  tickFormatter={compactAxis}
                  tick={{ fill: INK_SOFT, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={48}
                />
                <Tooltip
                  formatter={(value: number, name: string) => [
                    formatCurrency(String(value), currencyCode),
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
                  dot={{ r: multiPeriod ? 3 : 4 }}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="net_profit"
                  stroke={ACCENT_MUTED}
                  strokeWidth={2}
                  dot={{ r: multiPeriod ? 3 : 4 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-md border border-line/80 bg-surface p-4 lg:col-span-2">
          <h3 className="text-sm font-semibold text-ink">Expense mix</h3>
          <p className="mt-1 text-xs text-soft">
            Cost of sales, operating expenses, and depreciation — current period
          </p>
          {expenseData.length === 0 ? (
            <p className="mt-8 text-sm text-soft">
              No expense lines available for this period.
            </p>
          ) : (
            <div
              className="mt-2 h-56 w-full"
              data-testid="performance-expense-chart"
            >
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={expenseData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={48}
                    outerRadius={78}
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
                      formatCurrency(String(value), currencyCode),
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
                    height={36}
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
