"use client";

import {
  formatPresetRangeLabel,
  PERIOD_PRESET_OPTIONS,
  type PeriodPreset,
} from "@/lib/period-presets";

type GlPeriodFieldsProps = {
  periodPreset: PeriodPreset;
  periodStart: string;
  periodEnd: string;
  onPresetChange: (preset: PeriodPreset) => void;
  onPeriodStartChange: (value: string) => void;
  onPeriodEndChange: (value: string) => void;
};

/** GL conversion reporting-period presets + start/end date inputs. */
export function GlPeriodFields({
  periodPreset,
  periodStart,
  periodEnd,
  onPresetChange,
  onPeriodStartChange,
  onPeriodEndChange,
}: GlPeriodFieldsProps) {
  return (
    <>
      <div className="space-y-2 sm:col-span-2" data-testid="gl-period-presets">
        <div>
          <span className="mb-1 block text-sm text-stone-600">
            Reporting period
          </span>
          <p className="text-xs text-stone-500">
            Presets set start and end together so the conversion window matches
            what you intend.
          </p>
        </div>
        <div
          role="group"
          aria-label="Period presets"
          className="flex flex-wrap gap-2"
        >
          {PERIOD_PRESET_OPTIONS.map((option) => {
            const selected = periodPreset === option.id;
            return (
              <button
                key={option.id}
                type="button"
                data-testid={`period-preset-${option.id}`}
                aria-pressed={selected}
                onClick={() => onPresetChange(option.id)}
                className={
                  selected
                    ? "rounded border border-teal-800 bg-teal-800 px-3 py-1.5 text-sm font-medium text-white"
                    : "rounded border border-stone-300 bg-white px-3 py-1.5 text-sm font-medium text-stone-800 hover:border-stone-400"
                }
              >
                {option.label}
              </button>
            );
          })}
        </div>
        {periodStart && periodEnd ? (
          <p
            className="rounded border border-teal-200 bg-teal-50/80 px-3 py-2 text-sm font-medium text-teal-950"
            data-testid="gl-period-range-banner"
          >
            {formatPresetRangeLabel(periodStart, periodEnd)}
            {periodPreset !== "custom" ? (
              <span className="ml-2 font-normal text-teal-800/80">
                (
                {
                  PERIOD_PRESET_OPTIONS.find((o) => o.id === periodPreset)
                    ?.label
                }
                )
              </span>
            ) : (
              <span className="ml-2 font-normal text-teal-800/80">(Custom)</span>
            )}
          </p>
        ) : null}
        {periodPreset !== "custom" ? (
          <p className="text-xs text-stone-500">
            Choose Custom to edit dates manually.
          </p>
        ) : null}
      </div>
      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">Period start</span>
        <input
          type="date"
          data-testid="gl-period-start"
          className="w-full rounded border border-stone-300 px-3 py-2"
          value={periodStart}
          onChange={(e) => onPeriodStartChange(e.target.value)}
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">Period end</span>
        <input
          type="date"
          data-testid="gl-period-end"
          className="w-full rounded border border-stone-300 px-3 py-2"
          value={periodEnd}
          onChange={(e) => onPeriodEndChange(e.target.value)}
        />
      </label>
    </>
  );
}
