"use client";

import { useState } from "react";
import { FUNCTIONAL_CURRENCIES } from "@/lib/constants";
import type { CompanyEntityFormValues } from "@/lib/company-form";

export type { CompanyEntityFormValues } from "@/lib/company-form";
export { DEFAULT_MATERIALITY_PCT, DEFAULT_MATERIALITY_ABS } from "@/lib/company-form";

type CompanyEntityFormProps = {
  /** Prefill for edit mode; create mode leaves defaults. */
  initialValues?: Partial<CompanyEntityFormValues>;
  initialName?: string;
  namePlaceholder?: string;
  title?: string;
  intro?: React.ReactNode;
  currencyHint?: React.ReactNode;
  /** Shown under the currency field when the company already has trial balances. */
  currencyChangeWarning?: string | null;
  submitLabel: string;
  isPending?: boolean;
  errorMessage?: string | null;
  onSubmit: (values: CompanyEntityFormValues) => void;
  onCancel?: () => void;
  cancelLabel?: string;
};

export function CompanyEntityForm({
  initialValues,
  initialName = "",
  namePlaceholder = "Acme Ltd",
  title,
  intro,
  currencyHint,
  currencyChangeWarning = null,
  submitLabel,
  isPending = false,
  errorMessage = null,
  onSubmit,
  onCancel,
  cancelLabel = "Cancel",
}: CompanyEntityFormProps) {
  const [name, setName] = useState(initialValues?.name ?? initialName);
  const [functionalCurrency, setFunctionalCurrency] = useState(
    initialValues?.functionalCurrency ?? "GBP",
  );
  const [companyNumber, setCompanyNumber] = useState(
    initialValues?.companyNumber ?? "",
  );
  const [industry, setIndustry] = useState(initialValues?.industry ?? "");
  const [companyType, setCompanyType] = useState<"trading" | "holding">(
    initialValues?.companyType ?? "trading",
  );

  const currencyChanged =
    initialValues?.functionalCurrency != null &&
    functionalCurrency !== initialValues.functionalCurrency;

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (!name.trim()) return;
        onSubmit({
          name: name.trim(),
          functionalCurrency,
          companyNumber,
          industry,
          companyType,
        });
      }}
    >
      {title ? (
        <h2 className="text-lg font-semibold tracking-tight text-stone-900">{title}</h2>
      ) : null}
      {intro}

      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">Company name</span>
        <input
          required
          type="text"
          className="w-full rounded border border-stone-300 px-3 py-2"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={namePlaceholder}
          data-testid="company-form-name"
        />
      </label>

      {currencyHint}

      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">Functional currency</span>
        <select
          className="w-full rounded border border-stone-300 bg-white px-3 py-2"
          value={functionalCurrency}
          onChange={(event) => setFunctionalCurrency(event.target.value)}
          data-testid="company-form-currency"
        >
          {FUNCTIONAL_CURRENCIES.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
      </label>

      {currencyChanged && currencyChangeWarning ? (
        <p
          className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950"
          data-testid="company-currency-change-warning"
        >
          {currencyChangeWarning}
        </p>
      ) : null}

      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">
          Company number <span className="text-stone-400">(optional)</span>
        </span>
        <input
          type="text"
          className="w-full rounded border border-stone-300 px-3 py-2"
          value={companyNumber}
          onChange={(event) => setCompanyNumber(event.target.value)}
          placeholder="12345678"
          data-testid="company-form-number"
        />
      </label>

      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">Company type</span>
        <select
          className="w-full rounded border border-stone-300 bg-white px-3 py-2"
          value={companyType}
          onChange={(event) =>
            setCompanyType(event.target.value as "trading" | "holding")
          }
          data-testid="company-form-type"
        >
          <option value="trading">Trading (profit-oriented)</option>
          <option value="holding">Holding (balance-sheet focused)</option>
        </select>
        <span className="mt-1 block text-xs text-stone-500">
          Drives ISA 320-style materiality suggestions after statements are
          generated (trading → profit before tax; holding → equity). Changing
          type resurfaces the suggestion banner; existing thresholds are not
          overwritten.
        </span>
      </label>

      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">
          Industry <span className="text-stone-400">(optional)</span>
        </span>
        <input
          type="text"
          className="w-full rounded border border-stone-300 px-3 py-2"
          value={industry}
          onChange={(event) => setIndustry(event.target.value)}
          placeholder="Professional services"
          data-testid="company-form-industry"
        />
      </label>

      {errorMessage ? (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {errorMessage}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={!name.trim() || isPending}
          className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="company-form-submit"
        >
          {isPending ? "Saving…" : submitLabel}
        </button>
        {onCancel ? (
          <button
            type="button"
            disabled={isPending}
            onClick={onCancel}
            className="rounded border border-stone-300 px-4 py-2 text-sm font-medium text-stone-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {cancelLabel}
          </button>
        ) : null}
      </div>
    </form>
  );
}
