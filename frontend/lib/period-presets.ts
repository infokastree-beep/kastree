/** GL conversion reporting-period presets (calendar dates, local timezone). */

export type PeriodPreset =
  | "full_year"
  | "this_month"
  | "this_quarter"
  | "custom";

export type PeriodDateRange = {
  start: string;
  end: string;
};

export const PERIOD_PRESET_OPTIONS: ReadonlyArray<{
  id: PeriodPreset;
  label: string;
}> = [
  { id: "full_year", label: "Full year" },
  { id: "this_month", label: "This month" },
  { id: "this_quarter", label: "This quarter" },
  { id: "custom", label: "Custom" },
];

/** Format a calendar Y-M-D without UTC shift from Date#toISOString. */
export function formatIsoDate(
  year: number,
  monthIndex0: number,
  day: number,
): string {
  const month = String(monthIndex0 + 1).padStart(2, "0");
  const dayPart = String(day).padStart(2, "0");
  return `${year}-${month}-${dayPart}`;
}

export function toLocalIsoDate(date: Date): string {
  return formatIsoDate(date.getFullYear(), date.getMonth(), date.getDate());
}

export function lastDayOfMonth(year: number, monthIndex0: number): number {
  return new Date(year, monthIndex0 + 1, 0).getDate();
}

/** Calendar quarter containing monthIndex0 (0–11). */
export function quarterMonthBounds(monthIndex0: number): {
  startMonth: number;
  endMonth: number;
} {
  const startMonth = Math.floor(monthIndex0 / 3) * 3;
  return { startMonth, endMonth: startMonth + 2 };
}

/**
 * Resolve start/end for a named preset relative to `today`.
 * - Full year → Jan 1 – Dec 31 of today's year
 * - This month → first–last day of today's month
 * - This quarter → first–last day of today's calendar quarter
 */
export function rangeForPreset(
  preset: Exclude<PeriodPreset, "custom">,
  today: Date = new Date(),
): PeriodDateRange {
  const year = today.getFullYear();
  const month = today.getMonth();

  switch (preset) {
    case "full_year":
      return {
        start: formatIsoDate(year, 0, 1),
        end: formatIsoDate(year, 11, 31),
      };
    case "this_month": {
      return {
        start: formatIsoDate(year, month, 1),
        end: formatIsoDate(year, month, lastDayOfMonth(year, month)),
      };
    }
    case "this_quarter": {
      const { startMonth, endMonth } = quarterMonthBounds(month);
      return {
        start: formatIsoDate(year, startMonth, 1),
        end: formatIsoDate(
          year,
          endMonth,
          lastDayOfMonth(year, endMonth),
        ),
      };
    }
    default: {
      const _exhaustive: never = preset;
      return _exhaustive;
    }
  }
}

/** If start/end match a preset for `today`, return it; otherwise `custom`. */
export function detectPeriodPreset(
  start: string,
  end: string,
  today: Date = new Date(),
): PeriodPreset {
  for (const preset of ["full_year", "this_month", "this_quarter"] as const) {
    const range = rangeForPreset(preset, today);
    if (range.start === start && range.end === end) {
      return preset;
    }
  }
  return "custom";
}

/** en-GB readable label for an ISO date (UTC calendar parts). */
export function formatPresetDateLabel(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!match) return isoDate;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function formatPresetRangeLabel(start: string, end: string): string {
  return `${formatPresetDateLabel(start)} → ${formatPresetDateLabel(end)}`;
}
