"use client";

import { useState } from "react";
import { formatCurrency } from "@/lib/currency";
import {
  sizeAmountToApi,
  sizeEmployeesLabel,
  sizeEmployeesToApi,
  sizeMoneyLabel,
  type SizeInputFields,
  type SizeYearRequest,
} from "@/lib/size-inputs";

type YearFields = {
  turnover: string;
  balanceSheet: string;
  employees: string;
};

const EMPTY_YEAR: YearFields = { turnover: "", balanceSheet: "", employees: "" };

export function SizeInputs({
  firstPeriod,
  currency,
  inputs,
  message,
  canEdit,
  lockLabel,
  busy,
  error,
  onRecord,
}: {
  firstPeriod: boolean;
  currency: string | null;
  inputs: SizeInputFields;
  message: string | null;
  canEdit: boolean;
  lockLabel: string | null;
  busy: boolean;
  error: string | null;
  onRecord: (body: {
    current: SizeYearRequest;
    preceding: SizeYearRequest | null;
  }) => void;
}) {
  const [current, setCurrent] = useState<YearFields>(EMPTY_YEAR);
  const [preceding, setPreceding] = useState<YearFields>(EMPTY_YEAR);
  const [formError, setFormError] = useState<string | null>(null);
  const recorded = inputs.size_current_turnover != null;
  const editable = canEdit && lockLabel == null;

  function yearRequest(fields: YearFields): SizeYearRequest | null {
    const turnover = sizeAmountToApi(fields.turnover);
    const balanceSheet = sizeAmountToApi(fields.balanceSheet);
    const employees = sizeEmployeesToApi(fields.employees);
    if (turnover == null || balanceSheet == null || employees == null) {
      return null;
    }
    return {
      turnover,
      balance_sheet_total: balanceSheet,
      employees,
    };
  }

  return (
    <section
      className="mt-4 space-y-3 rounded-md border border-line bg-surface-elevated p-4"
      data-testid="statutory-size-inputs"
    >
      <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
        Size test
      </h3>
      {message ? (
        <p className="text-sm text-ink" data-testid="size-rule-message">
          {message}
        </p>
      ) : null}
      <dl className="grid max-w-xl gap-2 text-sm text-ink">
        <div className="flex justify-between gap-4">
          <dt>Turnover</dt>
          <dd data-testid="size-current-turnover">
            {sizeMoneyLabel(inputs.size_current_turnover, currency, formatCurrency)}
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Balance sheet total</dt>
          <dd data-testid="size-current-balance-sheet">
            {sizeMoneyLabel(inputs.size_current_balance_sheet, currency, formatCurrency)}
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Employees</dt>
          <dd data-testid="size-current-employees">
            {sizeEmployeesLabel(inputs.size_current_employees)}
          </dd>
        </div>
        {firstPeriod ? null : (
          <>
            <div className="flex justify-between gap-4">
              <dt>Preceding turnover</dt>
              <dd>{sizeMoneyLabel(inputs.size_preceding_turnover, currency, formatCurrency)}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt>Preceding balance sheet total</dt>
              <dd>
                {sizeMoneyLabel(
                  inputs.size_preceding_balance_sheet,
                  currency,
                  formatCurrency,
                )}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt>Preceding employees</dt>
              <dd>{sizeEmployeesLabel(inputs.size_preceding_employees)}</dd>
            </div>
          </>
        )}
      </dl>
      {recorded ? null : (
        <p className="text-sm text-ink" data-testid="size-inputs-missing">
          Size test inputs have not been recorded.
        </p>
      )}
      {lockLabel ? (
        <p className="text-sm font-semibold text-ink" data-testid="size-inputs-locked">
          {lockLabel}
        </p>
      ) : null}
      {editable ? (
        <form
          className="max-w-xl space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            const currentYear = yearRequest(current);
            const precedingYear = firstPeriod ? null : yearRequest(preceding);
            if (currentYear == null || (!firstPeriod && precedingYear == null)) {
              setFormError(
                "Enter a turnover, a balance sheet total in cents, and a whole number of employees.",
              );
              return;
            }
            setFormError(null);
            onRecord({ current: currentYear, preceding: precedingYear });
          }}
        >
          <YearFieldsInput
            legend="Current year"
            fields={current}
            onChange={setCurrent}
            prefix="size-current"
          />
          {firstPeriod ? (
            <p className="text-sm text-ink-secondary">
              This year end is a first financial period, so there is no preceding year.
            </p>
          ) : (
            <YearFieldsInput
              legend="Preceding year"
              fields={preceding}
              onChange={setPreceding}
              prefix="size-preceding"
            />
          )}
          {formError ? <p className="text-sm text-ink">{formError}</p> : null}
          {error ? <p className="text-sm text-ink">{error}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="rounded-md border border-line bg-surface px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
            data-testid="size-inputs-save"
          >
            Record size test
          </button>
        </form>
      ) : null}
    </section>
  );
}

function YearFieldsInput({
  legend,
  fields,
  onChange,
  prefix,
}: {
  legend: string;
  fields: YearFields;
  onChange: (next: YearFields) => void;
  prefix: string;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
        {legend}
      </legend>
      <label className="flex flex-col gap-1 text-sm">
        Turnover
        <input
          value={fields.turnover}
          onChange={(event) => onChange({ ...fields, turnover: event.target.value })}
          className="rounded-md border border-line bg-surface px-3 py-2"
          data-testid={`${prefix}-turnover-input`}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Balance sheet total
        <input
          value={fields.balanceSheet}
          onChange={(event) =>
            onChange({ ...fields, balanceSheet: event.target.value })
          }
          className="rounded-md border border-line bg-surface px-3 py-2"
          data-testid={`${prefix}-balance-sheet-input`}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Employees
        <input
          value={fields.employees}
          onChange={(event) => onChange({ ...fields, employees: event.target.value })}
          className="rounded-md border border-line bg-surface px-3 py-2"
          data-testid={`${prefix}-employees-input`}
        />
      </label>
    </fieldset>
  );
}
