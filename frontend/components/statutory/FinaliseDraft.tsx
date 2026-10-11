"use client";

import { useState } from "react";
import { blockingSentence } from "@/lib/dashboard-groups";
import {
  CARRIED_ACK_LABEL,
  FINALISE_LOCK_NOTE,
  canOfferFinalise,
  carriedAcknowledgementRequired,
  finalStateLabel,
} from "@/lib/finalise-status";

export function FinaliseDraft({
  role,
  status,
  canFinalise,
  blockingCount = 0,
  carriedDisclosures,
  wordingSignedOff = false,
  busy,
  onConfirm,
}: {
  role: string | undefined;
  status: string | undefined;
  canFinalise: boolean;
  blockingCount?: number;
  carriedDisclosures: readonly string[];
  wordingSignedOff?: boolean;
  busy?: boolean;
  onConfirm: (reviewedCarriedDisclosures: boolean) => Promise<string | null>;
}) {
  const [open, setOpen] = useState(false);
  const [acked, setAcked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const needsAck = carriedAcknowledgementRequired(carriedDisclosures);

  if (status === "final") {
    return (
      <p className="mt-2 text-sm font-semibold" data-testid="statutory-final-state">
        {finalStateLabel(wordingSignedOff)}
      </p>
    );
  }
  if (!canOfferFinalise(role, status)) {
    return null;
  }

  function close(): void {
    setOpen(false);
    setAcked(false);
    setError(null);
  }

  async function confirm(): Promise<void> {
    setError(null);
    const message = await onConfirm(needsAck ? acked : false);
    if (message) {
      setError(message);
      return;
    }
    close();
  }

  const reason = !canFinalise ? blockingSentence(blockingCount) : null;

  if (!open) {
    return (
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          data-testid="statutory-finalise"
          disabled={busy || !canFinalise}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground disabled:opacity-50"
          onClick={() => setOpen(true)}
        >
          Finalise
        </button>
        {reason ? (
          <p className="text-sm" data-testid="statutory-finalise-reason">
            {reason}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="statutory-finalise-title"
      data-testid="statutory-finalise-dialog"
      className="mt-3 max-w-xl space-y-3 rounded-md border border-line bg-surface-elevated p-4 text-ink"
    >
      <p id="statutory-finalise-title" className="text-sm">
        Finalise this draft? The stored statements will not change after this.
      </p>
      <p className="text-sm" data-testid="statutory-finalise-lock">
        {FINALISE_LOCK_NOTE}
      </p>
      {needsAck ? (
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            data-testid="statutory-finalise-ack"
            checked={acked}
            onChange={(event) => setAcked(event.target.checked)}
          />
          <span>{CARRIED_ACK_LABEL}</span>
        </label>
      ) : null}
      {error ? (
        <p className="text-sm text-red-800" data-testid="statutory-finalise-error">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="statutory-finalise-cancel"
          className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink"
          onClick={close}
        >
          Cancel
        </button>
        <button
          type="button"
          data-testid="statutory-finalise-confirm"
          disabled={busy || (needsAck && !acked)}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground disabled:opacity-50"
          onClick={() => void confirm()}
        >
          Finalise
        </button>
      </div>
    </div>
  );
}
