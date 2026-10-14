"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";

type NextYearPreview = {
  carries_over: string[];
  preparer_must: string[];
  period_start: string;
  period_end: string;
  year_end_id: string | null;
};

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "The next year could not be started.";
}

export function StartNextYear({
  yearEndId,
  canStart,
}: {
  yearEndId: string;
  canStart: boolean;
}) {
  const { getToken } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<NextYearPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!canStart) {
    return null;
  }

  async function ask(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const body = await apiFetch<NextYearPreview>(
        `/year-ends/${yearEndId}/start-next-year`,
        {
          method: "POST",
          getToken,
          body: JSON.stringify({ confirm: false }),
        },
      );
      setPreview(body);
      setOpen(true);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  async function confirm(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const body = await apiFetch<NextYearPreview>(
        `/year-ends/${yearEndId}/start-next-year`,
        {
          method: "POST",
          getToken,
          body: JSON.stringify({ confirm: true }),
        },
      );
      if (body.year_end_id) {
        router.push(`/year-ends/${body.year_end_id}/draft?section=review`);
      }
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2" data-testid="start-next-year">
      <button
        type="button"
        disabled={busy}
        onClick={() => void ask()}
        className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
      >
        Start next year
      </button>
      {error ? (
        <p className="text-sm text-red-800" data-testid="start-next-year-error">
          {error}
        </p>
      ) : null}
      {open && preview ? (
        <div
          className="space-y-3 rounded-md border border-line bg-surface-elevated p-4"
          data-testid="start-next-year-dialog"
          role="dialog"
          aria-label="Start next year"
        >
          <p className="text-sm text-ink">
            The next period runs from {preview.period_start} to {preview.period_end}.
          </p>
          <div>
            <h3 className="text-sm font-semibold text-ink">What carries over</h3>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink">
              {preview.carries_over.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-ink">What you must do</h3>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink">
              {preview.preparer_must.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => void confirm()}
              className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground disabled:opacity-50"
              data-testid="start-next-year-confirm"
            >
              Create the next year
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setOpen(false)}
              className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
              data-testid="start-next-year-cancel"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
