"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import {
  JURISDICTION_HINT,
  canEditPracticeJurisdiction,
  jurisdictionUpdateBody,
  type PracticeJurisdiction,
} from "@/lib/practice-jurisdiction";
import type { IOrganisation } from "@/types";

type UserMe = {
  role: string;
};

const OPTIONS: { value: PracticeJurisdiction; label: string }[] = [
  { value: null, label: "Not set" },
  { value: "IE", label: "Ireland" },
  { value: "GB", label: "United Kingdom" },
];

function asJurisdiction(value: string | null | undefined): PracticeJurisdiction {
  if (value === "IE" || value === "GB") {
    return value;
  }
  return null;
}

export function PracticeJurisdictionForm() {
  const { getToken, isLoaded } = useAuth();
  const queryClient = useQueryClient();
  const organisation = useQuery({
    queryKey: ["organisation", "me"],
    enabled: isLoaded,
    queryFn: () => apiFetch<IOrganisation>("/organisations/me", { getToken }),
  });
  const me = useQuery({
    queryKey: ["users", "me"],
    enabled: isLoaded,
    queryFn: () => apiFetch<UserMe>("/users/me", { getToken }),
  });
  const [draft, setDraft] = useState<PracticeJurisdiction | undefined>(undefined);
  const [savedFlash, setSavedFlash] = useState(false);
  const current = asJurisdiction(organisation.data?.jurisdiction);
  const selected = draft === undefined ? current : draft;
  const canEdit = canEditPracticeJurisdiction(me.data?.role);

  const save = useMutation({
    mutationFn: () =>
      apiFetch<IOrganisation>("/organisations/me", {
        method: "PUT",
        body: JSON.stringify(jurisdictionUpdateBody(selected)),
        getToken,
      }),
    onSuccess: (updated) => {
      setDraft(undefined);
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 2000);
      queryClient.setQueryData(["organisation", "me"], updated);
    },
  });

  const errorMessage =
    save.error instanceof ApiError || save.error instanceof Error
      ? save.error.message
      : save.error
        ? "Could not save the practice country"
        : null;

  return (
    <section
      className="max-w-lg rounded border border-stone-200 bg-white p-4"
      data-testid="practice-jurisdiction"
    >
      <h2 className="text-sm font-semibold text-stone-800">Practice country</h2>
      <p className="mt-1 text-sm text-stone-600" data-testid="practice-jurisdiction-hint">
        {JURISDICTION_HINT}
      </p>
      {organisation.isLoading ? (
        <p className="mt-3 text-sm text-stone-500">Loading…</p>
      ) : organisation.isError ? (
        <p className="mt-3 text-sm text-red-800">Could not load practice settings.</p>
      ) : (
        <label className="mt-3 block text-sm">
          <span className="mb-1 block text-stone-600">Country</span>
          <select
            className="w-full rounded border border-stone-300 bg-white px-3 py-2 disabled:bg-stone-100"
            value={selected ?? ""}
            disabled={!canEdit || save.isPending}
            onChange={(event) => {
              const next = event.target.value;
              setDraft(next === "IE" || next === "GB" ? next : null);
              setSavedFlash(false);
            }}
            data-testid="practice-jurisdiction-select"
          >
            {OPTIONS.map((option) => (
              <option key={option.label} value={option.value ?? ""}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {errorMessage ? (
        <p className="mt-2 text-sm text-red-800">{errorMessage}</p>
      ) : null}
      {canEdit ? (
        <div className="mt-3 flex items-center gap-3">
          <button
            type="button"
            className="rounded bg-stone-900 px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={save.isPending || selected === current || organisation.isLoading}
            onClick={() => save.mutate()}
            data-testid="practice-jurisdiction-save"
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
          {savedFlash ? (
            <span className="text-sm text-emerald-700">Saved</span>
          ) : null}
        </div>
      ) : me.isSuccess ? (
        <p className="mt-3 text-sm text-stone-500">
          An owner or admin sets the practice country.
        </p>
      ) : null}
    </section>
  );
}
