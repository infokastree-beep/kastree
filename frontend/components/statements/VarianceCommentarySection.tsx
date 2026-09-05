"use client";

import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { formatCanonicalLineLabel } from "@/lib/utils";
import type {
  CommentaryFeedbackResponse,
  VarianceItem,
  VarianceResponse,
} from "@/types";

type DraftState = {
  text: string;
  dirty: boolean;
  thumbs: boolean | null;
  savedHint: string | null;
};

function confidenceCaption(confidence: string | null | undefined): string {
  if (!confidence) return "Confidence unknown";
  return `${confidence.charAt(0).toUpperCase()}${confidence.slice(1)} confidence`;
}

export function VarianceCommentarySection({
  variance,
}: {
  variance: VarianceResponse;
}) {
  const { getToken } = useAuth();
  const varianceId = variance.variance_id ?? null;

  const materialWithCommentary = useMemo(
    () =>
      variance.items.filter(
        (item) => item.is_material && Boolean(item.commentary?.text),
      ),
    [variance.items],
  );

  const [drafts, setDrafts] = useState<Record<string, DraftState>>({});

  useEffect(() => {
    const next: Record<string, DraftState> = {};
    for (const item of materialWithCommentary) {
      next[item.line_item_code] = {
        text: item.commentary?.text ?? "",
        dirty: false,
        thumbs: null,
        savedHint: null,
      };
    }
    setDrafts(next);
  }, [materialWithCommentary, variance.variance_id]);

  const feedbackMutation = useMutation({
    mutationFn: async (payload: {
      lineItemCode: string;
      thumbsUp?: boolean | null;
      correctedText?: string | null;
    }) => {
      if (!varianceId) {
        throw new Error(
          "Variance analysis id is missing — refresh variance first.",
        );
      }
      return apiFetch<CommentaryFeedbackResponse>("/commentary/feedback", {
        method: "POST",
        getToken,
        body: JSON.stringify({
          variance_id: varianceId,
          line_item_code: payload.lineItemCode,
          thumbs_up: payload.thumbsUp ?? null,
          corrected_text: payload.correctedText ?? null,
        }),
      });
    },
  });

  function updateDraft(code: string, patch: Partial<DraftState>) {
    setDrafts((prev) => ({
      ...prev,
      [code]: { ...prev[code]!, ...patch },
    }));
  }

  async function saveEdit(item: VarianceItem) {
    const draft = drafts[item.line_item_code];
    if (!draft || !draft.dirty) return;
    await feedbackMutation.mutateAsync({
      lineItemCode: item.line_item_code,
      correctedText: draft.text,
    });
    updateDraft(item.line_item_code, {
      dirty: false,
      savedHint: "Saved correction",
    });
  }

  async function sendThumbs(item: VarianceItem, thumbsUp: boolean) {
    await feedbackMutation.mutateAsync({
      lineItemCode: item.line_item_code,
      thumbsUp,
    });
    updateDraft(item.line_item_code, {
      thumbs: thumbsUp,
      savedHint: thumbsUp ? "Marked helpful" : "Marked needs work",
    });
  }

  if (materialWithCommentary.length === 0) {
    return (
      <div
        className="rounded-md border border-line bg-surface-elevated p-5"
        data-testid="variance-commentary-empty"
      >
        <h3 className="font-display text-base font-semibold text-ink">
          AI commentary
        </h3>
        <p className="mt-2 text-sm text-ink-secondary">
          No AI commentary on file for this variance run. Refresh variance to
          draft commentary for material movements. Amounts are never sent to the
          model — only line names, directions, and percentage changes.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="variance-commentary-section">
      <div>
        <h3 className="font-display text-base font-semibold text-ink">
          AI commentary
        </h3>
        <p className="mt-1 text-sm text-ink-secondary">
          Draft wording for material variances. Edit before export or client
          review — thumbs train the prompt, they do not change the numbers.
        </p>
      </div>

      {feedbackMutation.error ? (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {feedbackMutation.error instanceof Error
            ? feedbackMutation.error.message
            : "Could not save commentary feedback"}
        </p>
      ) : null}

      <ul className="space-y-3">
        {materialWithCommentary.map((item) => {
          const draft = drafts[item.line_item_code];
          const commentary = item.commentary!;
          const reasoning = commentary.reasoning?.trim() || null;

          return (
            <li
              key={item.line_item_code}
              className="rounded-md border border-line bg-surface-elevated p-4"
              data-testid={`commentary-card-${item.line_item_code}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-ink">
                    {item.line_item_name ||
                      formatCanonicalLineLabel(item.line_item_code)}
                  </p>
                  <p className="mt-0.5 text-xs text-soft">
                    {confidenceCaption(commentary.confidence)}
                    {commentary.is_edited ? " · Edited" : " · AI draft"}
                    {item.variance_pct
                      ? ` · ${Number.parseFloat(item.variance_pct).toFixed(1)}% ${item.direction}`
                      : ` · ${item.direction}`}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    title={
                      reasoning
                        ? `Why this draft: ${reasoning}`
                        : "No reasoning provided"
                    }
                    className="rounded-md border border-line px-2.5 py-1.5 text-xs font-semibold text-ink-secondary transition-colors hover:border-accent hover:text-accent"
                    data-testid={`commentary-reasoning-${item.line_item_code}`}
                  >
                    Why?
                  </button>
                  <button
                    type="button"
                    aria-label="Thumbs up"
                    disabled={!varianceId || feedbackMutation.isPending}
                    onClick={() => void sendThumbs(item, true)}
                    className={`rounded-md border px-2.5 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 ${
                      draft?.thumbs === true
                        ? "border-accent bg-accent-muted text-accent"
                        : "border-line text-ink-secondary hover:border-accent hover:text-accent"
                    }`}
                  >
                    ▲
                  </button>
                  <button
                    type="button"
                    aria-label="Thumbs down"
                    disabled={!varianceId || feedbackMutation.isPending}
                    onClick={() => void sendThumbs(item, false)}
                    className={`rounded-md border px-2.5 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 ${
                      draft?.thumbs === false
                        ? "border-red-300 bg-red-50 text-red-800"
                        : "border-line text-ink-secondary hover:border-red-300 hover:text-red-800"
                    }`}
                  >
                    ▼
                  </button>
                </div>
              </div>

              <label className="mt-3 block">
                <span className="sr-only">
                  Commentary for {item.line_item_name}
                </span>
                <textarea
                  value={draft?.text ?? commentary.text}
                  onChange={(event) =>
                    updateDraft(item.line_item_code, {
                      text: event.target.value,
                      dirty: event.target.value !== commentary.text,
                      savedHint: null,
                    })
                  }
                  rows={3}
                  className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  data-testid={`commentary-text-${item.line_item_code}`}
                />
              </label>

              <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-soft">
                  {draft?.savedHint
                    ? draft.savedHint
                    : draft?.dirty
                      ? "Unsaved edits"
                      : reasoning
                        ? "Hover Why? for model reasoning"
                        : "Editable before anything leaves this screen"}
                </p>
                <button
                  type="button"
                  disabled={
                    !varianceId ||
                    !draft?.dirty ||
                    feedbackMutation.isPending ||
                    !draft?.text.trim()
                  }
                  onClick={() => void saveEdit(item)}
                  className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-accent-foreground transition-colors hover:bg-accent-hover disabled:opacity-50"
                >
                  {feedbackMutation.isPending ? "Saving…" : "Save edit"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
