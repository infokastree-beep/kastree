"use client";

import { useState } from "react";
import { FUNCTIONAL_CURRENCIES } from "@/lib/constants";
import {
  DEFAULT_MATERIALITY_ABS,
  DEFAULT_MATERIALITY_PCT,
  type CompanyEntityFormValues,
} from "@/lib/company-form";

export type { CompanyEntityFormValues } from "@/lib/company-form";
export { DEFAULT_MATERIALITY_ABS, DEFAULT_MATERIALITY_PCT } from "@/lib/company-form";

type CompanyEntityFormProps = {
  initialName?: string;
  intro?: React.ReactNode;
  submitLabel: string;
  isPending?: boolean;
  errorMessage?: string | null;
  onSubmit: (values: CompanyEntityFormValues) => void;
  onCancel?: () => void;
  cancelLabel?: string;
};

export function CompanyEntityForm({
  initialName = "",
  intro,
  submitLabel,
  isPending = false,
  errorMessage = null,
  onSubmit,
  onCancel,
  cancelLabel = "Cancel",
}: CompanyEntityFormProps) {
  const [name, setName] = useState(initialName);
  const [functionalCurrency, setFunctionalCurrency] = useState("GBP");
  const [companyNumber, setCompanyNumber] = useState("");
  const [industry, setIndustry] = useState("");
  const [materialityPct, setMaterialityPct] = useState(DEFAULT_MATERIALITY_PCT);
  const [materialityAbs, setMaterialityAbs] = useState(DEFAULT_MATERIALITY_ABS);

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
          materialityPct,
          materialityAbs,
        });
      }}
    >
      {intro}

      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">Company name</span>
        <input
          required
          type="text"
          className="w-full rounded border border-stone-300 px-3 py-2"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Acme Ltd"
        />
      </label>

      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">Functional currency</span>
        <select
          className="w-full rounded border border-stone-300 bg-white px-3 py-2"
          value={functionalCurrency}
          onChange={(event) => setFunctionalCurrency(event.target.value)}
        >
          {FUNCTIONAL_CURRENCIES.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
      </label>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block text-stone-600">Materiality %</span>
          <input
            type="number"
            min="0"
            step="0.01"
            className="w-full rounded border border-stone-300 px-3 py-2"
            value={materialityPct}
            onChange={(event) => setMaterialityPct(event.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-stone-600">Materiality absolute</span>
          <input
            type="number"
            min="0"
            step="0.01"
            className="w-full rounded border border-stone-300 px-3 py-2"
            value={materialityAbs}
            onChange={(event) => setMaterialityAbs(event.target.value)}
          />
        </label>
      </div>

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
        />
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
