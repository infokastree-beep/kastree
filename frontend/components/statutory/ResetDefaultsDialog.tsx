"use client";

import { useState } from "react";
import { RESET_CONFIRM_MESSAGE, resetConfirmAfter } from "@/lib/reset-confirm";

export function ResetDefaultsDialog({
  askTestId,
  confirmTestId,
  busy,
  onReset,
}: {
  askTestId: string;
  confirmTestId: string;
  busy?: boolean;
  onReset: () => void;
}) {
  const [open, setOpen] = useState(false);

  function act(action: "open" | "cancel" | "reset"): void {
    const next = resetConfirmAfter(open ? "open" : "closed", action);
    setOpen(next.state === "open");
    if (next.send) {
      onReset();
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        disabled={busy}
        data-testid={askTestId}
        className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
        onClick={() => act("open")}
      >
        Reset to pack defaults
      </button>
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={`${confirmTestId}-title`}
      data-testid={`${confirmTestId}-dialog`}
      className="max-w-xl space-y-3 rounded-md border border-line bg-surface-elevated p-4"
    >
      <p id={`${confirmTestId}-title`} className="text-sm text-ink">
        {RESET_CONFIRM_MESSAGE}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink"
          onClick={() => act("cancel")}
        >
          Cancel
        </button>
        <button
          type="button"
          disabled={busy}
          data-testid={confirmTestId}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground disabled:opacity-50"
          onClick={() => act("reset")}
        >
          Reset
        </button>
      </div>
    </div>
  );
}
