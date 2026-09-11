"use client";

import { useCallback, useState } from "react";
import { GlPeriodFields } from "@/components/upload/GlPeriodFields";
import {
  rangeForPreset,
  type PeriodPreset,
} from "@/lib/period-presets";

/**
 * Auth-free preview of GL conversion period presets.
 * Visit /dev/gl-period-presets while iterating on the Upload form controls.
 */
export default function GlPeriodPresetsPreviewPage() {
  const initial = rangeForPreset("full_year");
  const [periodPreset, setPeriodPreset] = useState<PeriodPreset>("full_year");
  const [periodStart, setPeriodStart] = useState(initial.start);
  const [periodEnd, setPeriodEnd] = useState(initial.end);

  const applyPeriodPreset = useCallback((preset: PeriodPreset) => {
    setPeriodPreset(preset);
    if (preset === "custom") return;
    const range = rangeForPreset(preset);
    setPeriodStart(range.start);
    setPeriodEnd(range.end);
  }, []);

  return (
    <main className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-stone-500">
          Dev preview
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-stone-900">
          GL conversion — period presets
        </h1>
        <p className="mt-2 text-sm text-stone-600">
          Same controls as Upload → General ledger. Selecting a preset fills
          Period start and Period end automatically.
        </p>
      </div>

      <div className="grid gap-4 rounded border border-stone-200 bg-white p-4 sm:grid-cols-2">
        <GlPeriodFields
          periodPreset={periodPreset}
          periodStart={periodStart}
          periodEnd={periodEnd}
          onPresetChange={applyPeriodPreset}
          onPeriodStartChange={(value) => {
            setPeriodStart(value);
            setPeriodPreset("custom");
          }}
          onPeriodEndChange={(value) => {
            setPeriodEnd(value);
            setPeriodPreset("custom");
          }}
        />
      </div>

      <dl className="grid grid-cols-2 gap-3 rounded border border-stone-200 bg-stone-50 px-4 py-3 text-sm">
        <div>
          <dt className="text-xs uppercase tracking-wide text-stone-400">
            Preset
          </dt>
          <dd className="font-medium text-stone-900" data-testid="preview-preset">
            {periodPreset}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-stone-400">
            ISO range
          </dt>
          <dd
            className="font-mono text-stone-900"
            data-testid="preview-iso-range"
          >
            {periodStart} → {periodEnd}
          </dd>
        </div>
      </dl>
    </main>
  );
}
