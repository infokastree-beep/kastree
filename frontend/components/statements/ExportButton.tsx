"use client";

/**
 * Export panel for the statements dashboard.
 *
 * Lifecycle:
 *   1. User picks a format (Excel / PDF / CSV) from the dropdown.
 *   2. POST /trial-balances/{tbId}/export → 202 { export_id }.
 *   3. Poll GET /exports/{export_id} every 1.5 s until status = "complete" | "failed".
 *   4. On complete: GET /exports/{id} for the presigned file_url, then
 *      trigger a real <a href={file_url}> navigation (not fetch + blob).
 *      Cross-origin fetch of the R2 302 is blocked by CORS; top-level
 *      navigation is not.
 *
 * Tier-gated watermarking is fully server-side — this component never passes
 * subscription_tier or watermark flags in the request body.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import type { ExportAcceptedResponse, ExportFormat, ExportStatusResponse } from "@/types";

const FORMAT_LABELS: Record<ExportFormat, string> = {
  xlsx: "Excel (.xlsx)",
  pdf: "PDF",
  csv: "CSV",
};

const POLL_INTERVAL_MS = 1500;
const MAX_POLLS = 60; // 90 s ceiling before giving up

type PhaseIdle = { phase: "idle" };
type PhaseSubmitting = { phase: "submitting"; format: ExportFormat };
type PhasePolling = { phase: "polling"; exportId: string; format: ExportFormat; polls: number };
type PhaseReady = { phase: "ready"; exportId: string; format: ExportFormat };
type PhaseFailed = { phase: "failed"; message: string };

type State = PhaseIdle | PhaseSubmitting | PhasePolling | PhaseReady | PhaseFailed;

export function ExportButton({ tbId }: { tbId: string }) {
  const { getToken } = useAuth();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<State>({ phase: "idle" });
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click.
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Clear any in-flight poll timer on unmount.
  useEffect(() => {
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, []);

  const pollStatus = useCallback(
    async (exportId: string, format: ExportFormat, polls: number) => {
      if (polls >= MAX_POLLS) {
        setState({ phase: "failed", message: "Export timed out. Please try again." });
        return;
      }
      try {
        const data = await apiFetch<ExportStatusResponse>(`/exports/${exportId}`, {
          getToken,
        });
        if (data.status === "complete") {
          setState({ phase: "ready", exportId, format });
          return;
        }
        if (data.status === "failed") {
          setState({
            phase: "failed",
            message: data.error_message ?? "Export failed. Please try again.",
          });
          return;
        }
        // pending or processing — keep polling
        setState({ phase: "polling", exportId, format, polls: polls + 1 });
        pollRef.current = setTimeout(
          () => pollStatus(exportId, format, polls + 1),
          POLL_INTERVAL_MS,
        );
      } catch (err) {
        setState({
          phase: "failed",
          message:
            err instanceof ApiError ? err.message : "Failed to check export status.",
        });
      }
    },
    [getToken],
  );

  const startExport = useCallback(
    async (format: ExportFormat) => {
      setOpen(false);
      setState({ phase: "submitting", format });
      if (pollRef.current) clearTimeout(pollRef.current);
      try {
        const accepted = await apiFetch<ExportAcceptedResponse>(
          `/trial-balances/${tbId}/export`,
          {
            method: "POST",
            body: JSON.stringify({ format }),
            getToken,
          },
        );
        setState({ phase: "polling", exportId: accepted.export_id, format, polls: 0 });
        pollRef.current = setTimeout(
          () => pollStatus(accepted.export_id, format, 0),
          POLL_INTERVAL_MS,
        );
      } catch (err) {
        setState({
          phase: "failed",
          message:
            err instanceof ApiError ? err.message : "Failed to start export.",
        });
      }
    },
    [tbId, getToken, pollStatus],
  );

  const handleDownload = useCallback(
    async (exportId: string) => {
      // Presigned file_url comes from GET /exports/{id} (Railway, CORS-ok).
      // Navigate to it with a real <a href> — never fetch() the R2 URL or the
      // /download 302, which the browser blocks as a cross-origin JS request.
      try {
        const data = await apiFetch<ExportStatusResponse>(`/exports/${exportId}`, {
          getToken,
        });
        if (!data.file_url) {
          setState({
            phase: "failed",
            message: "Export is complete but no download URL was returned.",
          });
          return;
        }
        const format = data.format;
        const a = document.createElement("a");
        a.href = data.file_url;
        a.download = `statements-${exportId.slice(0, 8)}.${format}`;
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } catch (err) {
        setState({
          phase: "failed",
          message:
            err instanceof ApiError ? err.message : "Download failed. Please try again.",
        });
      }
    },
    [getToken],
  );

  const reset = () => {
    if (pollRef.current) clearTimeout(pollRef.current);
    setState({ phase: "idle" });
  };

  const isBusy = state.phase === "submitting" || state.phase === "polling";

  return (
    <div className="flex items-center gap-2">
      {/* Status / result area */}
      {state.phase === "polling" || state.phase === "submitting" ? (
        <span className="flex items-center gap-1.5 text-sm text-stone-500">
          <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-stone-300 border-t-stone-600" />
          {state.phase === "submitting"
            ? `Starting ${FORMAT_LABELS[state.format]} export…`
            : `Building ${FORMAT_LABELS[(state as PhasePolling).format]}…`}
        </span>
      ) : null}

      {state.phase === "ready" ? (
        <span className="flex items-center gap-2 text-sm">
          <span className="text-stone-600">
            {FORMAT_LABELS[(state as PhaseReady).format]} ready
          </span>
          <button
            type="button"
            onClick={() => handleDownload((state as PhaseReady).exportId)}
            className="rounded bg-stone-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-stone-700"
          >
            Download
          </button>
          <button
            type="button"
            onClick={reset}
            className="text-xs text-stone-400 hover:text-stone-700"
          >
            ✕
          </button>
        </span>
      ) : null}

      {state.phase === "failed" ? (
        <span className="flex items-center gap-2">
          <span className="rounded border border-red-200 bg-red-50 px-2 py-1 text-sm text-red-800">
            {(state as PhaseFailed).message}
          </span>
          <button
            type="button"
            onClick={reset}
            className="text-xs text-stone-400 hover:text-stone-700"
          >
            ✕
          </button>
        </span>
      ) : null}

      {/* Format picker dropdown — always shown except when a download is ready */}
      {state.phase !== "ready" ? (
        <div className="relative" ref={dropdownRef}>
          <button
            type="button"
            disabled={isBusy}
            onClick={() => setOpen((o) => !o)}
            className="flex items-center gap-1.5 rounded border border-stone-300 bg-white px-3 py-1.5 text-sm font-medium text-stone-900 hover:bg-stone-50 disabled:opacity-50"
          >
            Export
            <svg
              className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06Z"
                clipRule="evenodd"
              />
            </svg>
          </button>

          {open ? (
            <div className="absolute right-0 z-20 mt-1 w-44 rounded border border-stone-200 bg-white py-1 shadow-lg">
              {(Object.entries(FORMAT_LABELS) as [ExportFormat, string][]).map(
                ([fmt, label]) => (
                  <button
                    key={fmt}
                    type="button"
                    onClick={() => startExport(fmt)}
                    className="block w-full px-4 py-2 text-left text-sm text-stone-700 hover:bg-stone-50"
                  >
                    {label}
                  </button>
                ),
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
