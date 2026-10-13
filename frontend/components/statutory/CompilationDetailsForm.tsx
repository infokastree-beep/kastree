"use client";

import { useState } from "react";
import { StatutoryLoadError } from "@/components/statutory/StatutoryLoadError";

const FIELD =
  "rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink disabled:opacity-50";

export type CompilationWrite = {
  compilation_date: string | null;
  compilation_signatory: string | null;
};

function textValue(value: string | null | undefined): string {
  return value ?? "";
}

function dateOrNull(value: string): string | null {
  return value === "" ? null : value;
}

export function CompilationDetailsForm({
  compilationDate,
  compilationSignatory,
  canEdit,
  busy,
  error,
  saved,
  onSave,
}: {
  compilationDate: string | null | undefined;
  compilationSignatory: string | null | undefined;
  canEdit: boolean;
  busy: boolean;
  error: string | null;
  saved: string | null;
  onSave: (next: CompilationWrite) => void;
}) {
  const locked = !canEdit || busy;
  const [recordedDate, setRecordedDate] = useState(textValue(compilationDate));
  const [signatory, setSignatory] = useState(textValue(compilationSignatory));

  return (
    <form
      className="space-y-4"
      data-testid="compilation-report-inputs"
      onSubmit={(event) => {
        event.preventDefault();
        onSave({
          compilation_date: dateOrNull(recordedDate),
          compilation_signatory: signatory.trim() === "" ? null : signatory.trim(),
        });
      }}
    >
      <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
        Date and signatory
      </h2>
      <p className="text-sm text-ink-secondary">
        This is the practice compilation report. It is separate from the
        directors&apos; approval of the financial statements.
      </p>
      <label className="flex max-w-xl flex-col gap-1.5 text-sm">
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Compilation date
        </span>
        <input
          type="date"
          value={recordedDate}
          disabled={locked}
          onChange={(event) => setRecordedDate(event.target.value)}
          className={FIELD}
          data-testid="compilation-date"
        />
      </label>
      <label className="flex max-w-xl flex-col gap-1.5 text-sm">
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Compilation signatory
        </span>
        <input
          value={signatory}
          disabled={locked}
          onChange={(event) => setSignatory(event.target.value)}
          className={FIELD}
          data-testid="compilation-signatory"
        />
      </label>
      {error !== null ? (
        <StatutoryLoadError
          testId="statutory-compilation-error"
          message={error}
          onReview={() => undefined}
        />
      ) : null}
      {saved !== null ? (
        <p className="text-sm text-emerald-800" data-testid="statutory-compilation-saved">
          {saved}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={locked}
        className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50"
        data-testid="compilation-save"
      >
        Save compilation report
      </button>
    </form>
  );
}
