"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "@/lib/api";
import { messageFromPdfBody } from "@/lib/workspace-load-error";
import {
  COMPARATIVES_NOTICE,
  FACE_DATES_DIFFER,
  FILE_NAME_NOT_RECORDED,
  recordedFileName,
  type TrialBalanceCandidate,
  type TrialBalancePage,
} from "@/lib/trial-balance-page";

const ADJUSTMENTS_NOTICE =
  "This draft's adjustments were made against a different trial balance";

type PreviewLine = {
  nominal_code: string;
  account_name: string;
  present: boolean;
};

type PreviewJournal = {
  narration: string;
  lines: PreviewLine[];
};

type PreviewBody = {
  detail: string;
  period_start: string;
  period_end: string;
  journals: PreviewJournal[];
  disclosure_answer_count: number;
  note_library_stored: boolean;
  draft_id: string;
  version_number: number;
};

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return messageFromPdfBody(error.body) ?? error.message;
  }
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}

function candidateLabel(row: TrialBalanceCandidate): string {
  const currency = row.currency ? ` · ${row.currency}` : "";
  const accounts =
    row.account_count == null ? "" : ` · ${row.account_count} accounts`;
  return `${row.period_start} to ${row.period_end} · ${recordedFileName(row.file_name)}${accounts}${currency}`;
}

export function TrialBalanceSwitch({
  yearEndId,
  page,
  canPrepare,
  rowVersion,
  getToken,
  previewItems,
}: {
  yearEndId: string;
  page: TrialBalancePage;
  canPrepare: boolean;
  rowVersion: number | null;
  getToken: () => Promise<string | null>;
  previewItems?: TrialBalanceCandidate[];
}) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewBody | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const candidates = useQuery({
    queryKey: ["trial-balance-candidates", yearEndId],
    queryFn: () =>
      apiFetch<{ items: TrialBalanceCandidate[] }>(
        `/year-ends/${yearEndId}/trial-balance/candidates`,
        { getToken },
      ),
    enabled: previewItems == null,
  });
  const items = previewItems ?? candidates.data?.items ?? [];

  async function previewAdopt(trialBalanceId: string): Promise<void> {
    if (rowVersion == null) return;
    const fixture = previewItems?.find((row) => row.id === trialBalanceId);
    if (fixture != null) {
      setSelectedId(trialBalanceId);
      setError(null);
      setPreview({
        detail: "Confirm the trial balance switch before it is saved.",
        period_start: fixture.period_start,
        period_end: fixture.period_end,
        journals: [
          {
            narration: "Present accounts",
            lines: [
              {
                nominal_code: "2130",
                account_name: "Bank current account",
                present: true,
              },
            ],
          },
          {
            narration: "Account missing from the new file",
            lines: [
              {
                nominal_code: "7100",
                account_name: "Admin overhead",
                present: false,
              },
            ],
          },
        ],
        disclosure_answer_count: 1,
        note_library_stored: true,
        draft_id: "preview",
        version_number: 1,
      });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/year-ends/${yearEndId}/trial-balance/adopt`, {
        method: "POST",
        getToken,
        body: JSON.stringify({
          trial_balance_id: trialBalanceId,
          row_version: rowVersion,
          confirm: false,
        }),
      });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 422 && isPreview(caught.body)) {
        setSelectedId(trialBalanceId);
        setPreview(previewOf(caught.body));
      } else {
        setPreview(null);
        setError(messageFrom(caught));
      }
    } finally {
      setBusy(false);
    }
  }

  async function confirmAdopt(): Promise<void> {
    if (preview == null || rowVersion == null || selectedId == null) return;
    const trialBalanceId = selectedId;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/year-ends/${yearEndId}/trial-balance/adopt`, {
        method: "POST",
        getToken,
        body: JSON.stringify({
          trial_balance_id: trialBalanceId,
          row_version: rowVersion,
          confirm: true,
        }),
      });
      setSelectedId(null);
      setPreview(null);
      await queryClient.invalidateQueries({ queryKey: ["trial-balance-page", yearEndId] });
      await queryClient.invalidateQueries({ queryKey: ["trial-balance-candidates", yearEndId] });
      await queryClient.invalidateQueries({ queryKey: ["draft-dashboard", yearEndId] });
      await queryClient.invalidateQueries({ queryKey: ["statutory-year-end", yearEndId] });
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  async function confirmAdjustments(): Promise<void> {
    if (rowVersion == null) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/year-ends/${yearEndId}/trial-balance/adjustments-confirmed`, {
        method: "POST",
        getToken,
        body: JSON.stringify({ row_version: rowVersion }),
      });
      await queryClient.invalidateQueries({ queryKey: ["trial-balance-page", yearEndId] });
      await queryClient.invalidateQueries({ queryKey: ["draft-dashboard", yearEndId] });
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  const notice = page.adjustments_notice;
  return (
    <div className="space-y-4" data-testid="statutory-trial-balance-switch">
      {notice ? (
        <p className="text-sm text-ink" data-testid="statutory-adjustments-notice">
          {notice}
        </p>
      ) : null}
      {page.face_dates_notice ? (
        <p className="text-sm text-ink" data-testid="statutory-face-dates-differ">
          {page.face_dates_notice}
        </p>
      ) : null}
      {page.comparatives_notice ? (
        <p className="text-sm text-ink" data-testid="statutory-comparatives-notice">
          {page.comparatives_notice}
        </p>
      ) : null}
      {notice && canPrepare ? (
        <button
          type="button"
          className="rounded border border-line px-3 py-2 text-sm"
          disabled={busy || rowVersion == null}
          onClick={() => void confirmAdjustments()}
        >
          Confirm adjustments
        </button>
      ) : null}
      {page.switch_refusal ? (
        <p className="text-sm text-ink-secondary" data-testid="statutory-switch-refusal">
          {page.switch_refusal}
        </p>
      ) : null}
      <h3 className="text-sm font-semibold text-ink">Use a different trial balance</h3>
      {previewItems == null && candidates.isLoading ? (
        <p className="text-sm text-soft">Loading trial balances…</p>
      ) : null}
      {items.length === 0 && (previewItems != null || candidates.data) ? (
        <p className="text-sm text-ink-secondary">No other trial balance is complete.</p>
      ) : null}
      <ul className="space-y-3">
        {items.map((row) => (
          <li key={row.id} className="text-sm" data-testid="statutory-tb-candidate">
            <p>{candidateLabel(row)}</p>
            {row.refusal ? (
              <p className="text-ink-secondary" data-testid="statutory-tb-candidate-refusal">
                {row.refusal}
              </p>
            ) : null}
            {row.ready && canPrepare && page.can_switch ? (
              <button
                type="button"
                className="mt-1 rounded border border-line px-3 py-2 text-sm"
                disabled={busy || rowVersion == null}
                onClick={() => void previewAdopt(row.id)}
              >
                Review this file
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {preview ? (
        <div className="space-y-2 rounded border border-line px-3 py-3" data-testid="statutory-readopt-preview">
          <p className="text-sm">{preview.detail}</p>
          <p className="text-sm">
            Period {preview.period_start} to {preview.period_end}. Draft version {preview.version_number}.{" "}
            {preview.disclosure_answer_count} disclosure answers kept.
            {preview.note_library_stored ? " A note library is stored." : " No note library is stored."}
          </p>
          {preview.journals.map((journal) => (
            <div key={journal.narration}>
              <p className="text-sm font-medium">{journal.narration}</p>
              <ul>
                {journal.lines.map((line) => (
                  <li key={`${line.nominal_code}-${line.account_name}`} className="text-sm">
                    {line.nominal_code} {line.account_name}{" "}
                    {line.present ? "is on the new file" : "is not on the new file"}
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {canPrepare ? (
            <button
              type="button"
              className="rounded bg-stone-900 px-3 py-2 text-sm text-white"
              disabled={busy}
              onClick={() => void confirmAdopt()}
            >
              Adopt this trial balance
            </button>
          ) : null}
        </div>
      ) : null}
      {error ? <p className="text-sm text-red-800">{error}</p> : null}
    </div>
  );
}

function isPreview(body: unknown): boolean {
  return previewOf(body) != null;
}

function previewOf(body: unknown): PreviewBody | null {
  if (typeof body !== "object" || body == null) return null;
  const record = body as Record<string, unknown>;
  const source =
    typeof record.detail === "object" && record.detail != null
      ? (record.detail as Record<string, unknown>)
      : record;
  if (!Array.isArray(source.journals) || typeof source.draft_id !== "string") return null;
  return source as unknown as PreviewBody;
}

export const trialBalanceSwitchCopy = {
  adjustments: ADJUSTMENTS_NOTICE,
  faceDates: FACE_DATES_DIFFER,
  comparatives: COMPARATIVES_NOTICE,
  fileName: FILE_NAME_NOT_RECORDED,
};
