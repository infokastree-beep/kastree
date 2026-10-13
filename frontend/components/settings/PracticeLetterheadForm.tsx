"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import {
  LETTERHEAD_HINT,
  canEditPracticeLetterhead,
  letterheadUpdateBody,
  type PracticeLetterhead,
} from "@/lib/practice-letterhead";
import type { IOrganisation } from "@/types";

type UserMe = {
  role: string;
};

function recorded(value: string | null | undefined): string {
  return value ?? "";
}

export function PracticeLetterheadForm() {
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
  const [draft, setDraft] = useState<PracticeLetterhead | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);
  const current: PracticeLetterhead = {
    name: recorded(organisation.data?.name),
    letterhead_address: recorded(organisation.data?.letterhead_address),
    letterhead_contact: recorded(organisation.data?.letterhead_contact),
  };
  const selected = draft ?? current;
  const canEdit = canEditPracticeLetterhead(me.data?.role);
  const unchanged =
    selected.name === current.name &&
    selected.letterhead_address === current.letterhead_address &&
    selected.letterhead_contact === current.letterhead_contact;

  const save = useMutation({
    mutationFn: () =>
      apiFetch<IOrganisation>("/organisations/me", {
        method: "PUT",
        body: JSON.stringify(letterheadUpdateBody(selected)),
        getToken,
      }),
    onSuccess: (updated) => {
      setDraft(null);
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 2000);
      queryClient.setQueryData(["organisation", "me"], updated);
    },
  });

  const errorMessage =
    save.error instanceof ApiError || save.error instanceof Error
      ? save.error.message
      : save.error
        ? "Could not save the practice letterhead"
        : null;

  function change(field: keyof PracticeLetterhead, value: string) {
    setDraft({ ...selected, [field]: value });
    setSavedFlash(false);
  }

  return (
    <section
      id="practice-letterhead"
      className="mt-6 max-w-lg rounded border border-stone-200 bg-white p-4"
      data-testid="practice-letterhead"
    >
      <h2 className="text-sm font-semibold text-stone-800">Practice letterhead</h2>
      <p className="mt-1 text-sm text-stone-600" data-testid="practice-letterhead-hint">
        {LETTERHEAD_HINT}
      </p>
      {organisation.isLoading ? (
        <p className="mt-3 text-sm text-stone-500">Loading…</p>
      ) : organisation.isError ? (
        <p className="mt-3 text-sm text-red-800">Could not load the practice letterhead.</p>
      ) : (
        <div className="mt-3 space-y-3">
          <label className="block text-sm">
            <span className="mb-1 block text-stone-600">Legal name</span>
            <input
              className="w-full rounded border border-stone-300 bg-white px-3 py-2 disabled:bg-stone-100"
              value={selected.name}
              disabled={!canEdit || save.isPending}
              onChange={(event) => change("name", event.target.value)}
              data-testid="practice-letterhead-name"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-stone-600">Address</span>
            <textarea
              className="w-full rounded border border-stone-300 bg-white px-3 py-2 disabled:bg-stone-100"
              rows={3}
              value={selected.letterhead_address}
              disabled={!canEdit || save.isPending}
              onChange={(event) => change("letterhead_address", event.target.value)}
              data-testid="practice-letterhead-address"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-stone-600">Contact</span>
            <input
              className="w-full rounded border border-stone-300 bg-white px-3 py-2 disabled:bg-stone-100"
              value={selected.letterhead_contact}
              disabled={!canEdit || save.isPending}
              onChange={(event) => change("letterhead_contact", event.target.value)}
              data-testid="practice-letterhead-contact"
            />
          </label>
        </div>
      )}
      {errorMessage ? (
        <p className="mt-2 text-sm text-red-800">{errorMessage}</p>
      ) : null}
      {canEdit ? (
        <div className="mt-3 flex items-center gap-3">
          <button
            type="button"
            className="rounded bg-stone-900 px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={
              save.isPending ||
              unchanged ||
              organisation.isLoading ||
              selected.name.trim() === ""
            }
            onClick={() => save.mutate()}
            data-testid="practice-letterhead-save"
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
          {savedFlash ? (
            <span className="text-sm text-emerald-700">Saved</span>
          ) : null}
        </div>
      ) : me.isSuccess ? (
        <p className="mt-3 text-sm text-stone-500">
          An owner or an administrator records the practice letterhead.
        </p>
      ) : null}
    </section>
  );
}
