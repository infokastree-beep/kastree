"use client";

import { PdfExtractReview } from "@/components/upload/PdfExtractReview";
import fixture from "./fixture.json";

/**
 * Dev-only preview of the GL → TB review step (no Clerk).
 * Open /dev/gl-tb-review-preview after convert-gl UI copy changes.
 */
export default function GlTbReviewPreviewPage() {
  // Preview only — confirm is a no-op (PdfExtractReview still requires the prop).
  const onConfirm = () => {
    /* no-op */
  };

  return (
    <main className="mx-auto max-w-5xl space-y-4 p-6">
      <p className="text-xs text-stone-500">
        Dev preview — Apex Manufacturing GL 2025 Mode C convert
      </p>
      <PdfExtractReview
        rows={fixture.rows}
        method={`gl_mode_${fixture.mode}`}
        title="Review generated trial balance"
        description="These are the real computed closing balances from your general ledger for the period below — not a preview or sample. Check them carefully before continuing to mapping."
        periodStart={fixture.period_start}
        periodEnd={fixture.period_end}
        warnings={[
          ...fixture.warnings,
          `Included ${fixture.included_count} ledger lines, excluded ${fixture.excluded_count}, openings ${fixture.opening_count}.`,
        ]}
        confirmLabel="Confirm and continue to mapping"
        onConfirm={onConfirm}
        onCancel={() => undefined}
      />
    </main>
  );
}
