"use client";

import { useState } from "react";
import type { RoundingMode, StatementType } from "@/lib/report-display";
import type { ReportingFramework } from "@/lib/workspace-sections";

export type FaceDates = {
  current_start: string | null;
  current_end: string | null;
  prior_start: string | null;
  prior_end: string | null;
};

export type ColumnHeaders = {
  as_at_current: string;
  as_at_prior: string;
  ended_current: string;
  ended_prior: string;
};

export type ReportSetup = {
  basis_id: string;
  basis_version: string;
  basis_label: string;
  rounding: RoundingMode;
  statement_type: StatementType;
  face_dates: FaceDates;
  column_headers: ColumnHeaders;
  trial_balance_period_start: string | null;
  trial_balance_period_end: string;
  sections?: Record<string, boolean> | null;
};

export type ReportSetupWrite = {
  rounding: RoundingMode;
  statement_type: StatementType;
  face_dates: FaceDates;
  column_headers: ColumnHeaders;
  sections?: Record<string, boolean> | null;
};

const STATEMENT_TYPES: StatementType[] = ["draft", "compilation"];

function dateValue(value: string | null): string {
  return value ?? "";
}

export function ReportSetupForm({
  frameworks,
  setup,
  busy,
  onSave,
}: {
  frameworks: readonly ReportingFramework[];
  setup: ReportSetup;
  busy: boolean;
  onSave: (next: ReportSetupWrite) => void;
}) {
  const [rounding, setRounding] = useState<RoundingMode>(setup.rounding);
  const [statementType, setStatementType] = useState<StatementType>(
    setup.statement_type,
  );
  const [dates, setDates] = useState<FaceDates>(setup.face_dates);
  const [headers, setHeaders] = useState<ColumnHeaders>(setup.column_headers);
  const choices = frameworks.filter(
    (framework) => framework.available || framework.id === setup.basis_id,
  );

  function setDate(key: keyof FaceDates, value: string): void {
    setDates((current) => ({ ...current, [key]: value === "" ? null : value }));
  }

  function setHeader(key: keyof ColumnHeaders, value: string): void {
    setHeaders((current) => ({ ...current, [key]: value }));
  }

  const datesDiffer =
    dates.current_start !== setup.trial_balance_period_start ||
    dates.current_end !== setup.trial_balance_period_end ||
    dates.prior_start !== null ||
    dates.prior_end !== null;

  return (
    <form
      className="space-y-4"
      data-testid="report-setup"
      onSubmit={(event) => {
        event.preventDefault();
        onSave({
          rounding,
          statement_type: statementType,
          face_dates: dates,
          column_headers: headers,
        });
      }}
    >
      <label className="flex max-w-xl flex-col gap-1.5 text-sm">
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Basis of preparation
        </span>
        <select
          data-testid="report-basis"
          className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink"
          value={setup.basis_id}
          onChange={() => undefined}
        >
          {choices.map((framework) => (
            <option key={framework.id} value={framework.id}>
              {framework.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex max-w-xl flex-col gap-1.5 text-sm">
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Rounding display
        </span>
        <select
          data-testid="report-rounding"
          className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink"
          value={rounding}
          onChange={(event) => setRounding(event.target.value as RoundingMode)}
        >
          <option value="unit">Nearest euro</option>
          <option value="thousands">Nearest €&apos;000</option>
        </select>
      </label>

      <fieldset className="space-y-2">
        <legend className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Face dates
        </legend>
        <p className="max-w-3xl text-sm text-ink-secondary">
          Printed on the face. The trial balance period is{" "}
          {setup.trial_balance_period_start ?? "—"} to{" "}
          {setup.trial_balance_period_end}.
        </p>
        {datesDiffer ? (
          <p className="text-sm text-amber-950" data-testid="report-dates-differ">
            These dates differ from the trial balance period. The figures stay
            on that trial balance.
          </p>
        ) : null}
        <div className="grid gap-2 sm:grid-cols-2">
          {(
            [
              ["current_start", "Current start"],
              ["current_end", "Current end"],
              ["prior_start", "Prior start"],
              ["prior_end", "Prior end"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex flex-col gap-1 text-sm">
              <span>{label}</span>
              <input
                type="date"
                data-testid={`report-date-${key}`}
                value={dateValue(dates[key])}
                onChange={(event) => setDate(key, event.target.value)}
                className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm"
              />
            </label>
          ))}
        </div>
      </fieldset>

      <label className="flex max-w-xl flex-col gap-1.5 text-sm">
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Statement type
        </span>
        <select
          data-testid="report-statement-type"
          className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink"
          value={statementType}
          onChange={(event) =>
            setStatementType(event.target.value as StatementType)
          }
        >
          {STATEMENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type === "draft" ? "Draft" : "Compilation"}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="grid gap-2 sm:grid-cols-2">
        <legend className="col-span-full text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Column headers
        </legend>
        {(
          [
            ["as_at_current", "As at, current"],
            ["as_at_prior", "As at, prior"],
            ["ended_current", "Ended, current"],
            ["ended_prior", "Ended, prior"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="flex flex-col gap-1 text-sm">
            <span>{label}</span>
            <input
              data-testid={`report-header-${key}`}
              value={headers[key]}
              onChange={(event) => setHeader(key, event.target.value)}
              className="rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm"
            />
          </label>
        ))}
      </fieldset>

      <button
        type="submit"
        disabled={busy}
        data-testid="report-setup-save"
        className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground disabled:opacity-50"
      >
        Save report setup
      </button>
    </form>
  );
}
