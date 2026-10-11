"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { ASK_OWNER, statutoryGateDiagnosis } from "@/lib/statutory-gate";

type BetaPosition = {
  statement: string;
};

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong";
}

function canTurnOn(role: string | undefined): boolean {
  return role === "owner" || role === "admin";
}

export function StatutoryOptInPanel({
  email,
  role,
  statement,
  pending,
  error,
  onConfirm,
  heading = true,
}: {
  email: string | null | undefined;
  role: string | undefined;
  statement: string | null;
  pending: boolean;
  error: string | null;
  onConfirm: () => Promise<void>;
  heading?: boolean;
}) {
  // This tick exists only while the panel is open. It is not stored.
  const [ticked, setTicked] = useState(false);
  const turnOn = canTurnOn(role);

  return (
    <div className="space-y-3" data-testid="statutory-opt-in">
      {heading ? (
        <h1 className="text-2xl font-semibold tracking-tight">Statutory accounts</h1>
      ) : null}
      {turnOn ? (
        <form
          className="space-y-3"
          autoComplete="off"
          onSubmit={(event) => {
            event.preventDefault();
            if (!ticked || pending) {
              return;
            }
            void onConfirm();
          }}
        >
          <p className="max-w-3xl text-sm text-ink-secondary" data-testid="statutory-opt-in-statement">
            {statement ?? "Loading the acknowledgement…"}
          </p>
          <label className="flex items-start gap-2 text-sm text-ink">
            <input
              type="checkbox"
              className="mt-1"
              checked={ticked}
              data-testid="statutory-opt-in-checkbox"
              onChange={(event) => setTicked(event.target.checked)}
            />
            <span>I have read this and the practice will review every output itself.</span>
          </label>
          <button
            type="submit"
            className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            disabled={!ticked || pending}
            data-testid="statutory-opt-in-confirm"
          >
            {pending ? "Saving…" : "Confirm"}
          </button>
        </form>
      ) : (
        <p className="text-sm text-ink-secondary" data-testid="statutory-opt-in-ask">
          {ASK_OWNER}
        </p>
      )}
      {error ? (
        <p className="text-sm text-red-800" data-testid="statutory-opt-in-error">
          {error}
        </p>
      ) : null}
      <p className="text-sm text-ink-secondary" data-testid="statutory-signoff-diagnosis">
        {statutoryGateDiagnosis(email)}
      </p>
    </div>
  );
}

export function StatutoryOptIn({
  email,
  role,
  heading = true,
}: {
  email: string | null | undefined;
  role: string | undefined;
  heading?: boolean;
}) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const turnOn = canTurnOn(role);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const position = useQuery({
    queryKey: ["beta-position"],
    queryFn: () => apiFetch<BetaPosition>("/beta", { getToken }),
    enabled: turnOn,
  });

  async function onConfirm(): Promise<void> {
    setPending(true);
    setError(null);
    try {
      await apiFetch("/beta/acknowledgement", {
        method: "POST",
        getToken,
        body: JSON.stringify({ accepted: true }),
      });
      await queryClient.invalidateQueries({ queryKey: ["users", "me"] });
      await queryClient.invalidateQueries({ queryKey: ["beta-position"] });
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setPending(false);
    }
  }

  const positionError = position.error ? messageFrom(position.error) : null;
  return (
    <StatutoryOptInPanel
      email={email}
      role={role}
      statement={position.data?.statement ?? null}
      pending={pending}
      error={error ?? positionError}
      onConfirm={onConfirm}
      heading={heading}
    />
  );
}
