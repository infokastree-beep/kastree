"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api";
import { updateCompanyMateriality } from "@/lib/companies";
import type { ICompany } from "@/types";

/**
 * Manual materiality thresholds for an existing company.
 * Independent of the ISA 320 suggestion banner on the statements dashboard.
 */
export function CompanyMaterialitySettings({ company }: { company: ICompany }) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [pct, setPct] = useState(company.materiality_threshold_pct);
  const [abs, setAbs] = useState(company.materiality_threshold_abs);
  const [savedFlash, setSavedFlash] = useState(false);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateCompanyMateriality(
        company.id,
        { materialityPct: pct.trim(), materialityAbs: abs.trim() },
        getToken,
      ),
    onSuccess: (updated) => {
      setPct(updated.materiality_threshold_pct);
      setAbs(updated.materiality_threshold_abs);
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 2000);
      void queryClient.invalidateQueries({
        queryKey: ["companies", company.client_id],
      });
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
      void queryClient.invalidateQueries({
        queryKey: ["tb-materiality-suggestion"],
      });
      void queryClient.invalidateQueries({ queryKey: ["tb-variance"] });
    },
  });

  const dirty =
    pct.trim() !== company.materiality_threshold_pct ||
    abs.trim() !== company.materiality_threshold_abs;

  const errorMessage =
    saveMutation.error instanceof ApiError || saveMutation.error instanceof Error
      ? saveMutation.error.message
      : saveMutation.error
        ? "Failed to save materiality"
        : null;

  return (
    <div
      className="rounded border border-stone-100 bg-stone-50/80 p-3"
      data-testid="company-materiality-settings"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">
        Materiality thresholds
      </p>
      <p className="mt-1 text-xs text-stone-500">
        Set your own percentage and absolute values. Independent of the ISA 320
        suggestion banner.
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block text-stone-600">Percentage (%)</span>
          <input
            type="number"
            min="0"
            step="0.01"
            className="w-full rounded border border-stone-300 bg-white px-3 py-2"
            value={pct}
            onChange={(event) => setPct(event.target.value)}
            data-testid="company-materiality-pct"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-stone-600">Absolute amount</span>
          <input
            type="number"
            min="0"
            step="0.01"
            className="w-full rounded border border-stone-300 bg-white px-3 py-2"
            value={abs}
            onChange={(event) => setAbs(event.target.value)}
            data-testid="company-materiality-abs"
          />
        </label>
      </div>
      {errorMessage ? (
        <p className="mt-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {errorMessage}
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={!dirty || saveMutation.isPending || !pct.trim() || !abs.trim()}
          onClick={() => saveMutation.mutate()}
          className="rounded bg-stone-900 px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="company-materiality-save"
        >
          {saveMutation.isPending ? "Saving…" : "Save materiality"}
        </button>
        {savedFlash ? (
          <span
            className="text-sm text-emerald-700"
            data-testid="company-materiality-saved"
          >
            Saved
          </span>
        ) : null}
      </div>
    </div>
  );
}
