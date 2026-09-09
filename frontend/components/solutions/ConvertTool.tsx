"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import {
  PdfExtractReview,
  type EditableExtractedRow,
} from "@/components/upload/PdfExtractReview";
import { apiFetch } from "@/lib/api";
import type { PdfTbExtractResponse } from "@/types";

type Step = "upload" | "review" | "redirecting";

/**
 * Standalone Convert tool — public, no Clerk.
 * Reuses Phase 1 extract + PdfExtractReview. Does NOT call /trial-balances/upload.
 */
export function ConvertTool() {
  const [step, setStep] = useState<Step>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [extract, setExtract] = useState<PdfTbExtractResponse | null>(null);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const abortRef = useRef(false);

  useEffect(() => {
    abortRef.current = false;
    return () => {
      abortRef.current = true;
    };
  }, []);

  const onPick = useCallback((next: File | null) => {
    setError(null);
    setExtract(null);
    setStep("upload");
    if (!next) {
      setFile(null);
      return;
    }
    const lower = next.name.toLowerCase();
    if (!lower.endsWith(".pdf") && !lower.endsWith(".csv")) {
      setError("Upload a trial balance as .pdf or .csv.");
      setFile(null);
      return;
    }
    if (next.size > 50 * 1024 * 1024) {
      setError("File exceeds the 50MB limit.");
      setFile(null);
      return;
    }
    setFile(next);
  }, []);

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragOver(false);
      onPick(event.dataTransfer.files?.[0] ?? null);
    },
    [onPick],
  );

  const runExtractOrPreview = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const lower = file.name.toLowerCase();
      if (lower.endsWith(".pdf")) {
        const form = new FormData();
        form.append("file", file);
        const data = await apiFetch<PdfTbExtractResponse>(
          "/solutions/convert/extract",
          { method: "POST", body: form },
        );
        if (abortRef.current) return;
        setExtract(data);
        setStep("review");
        return;
      }
      const text = await file.text();
      const lines = text.split(/\r?\n/).filter((l) => l.trim());
      if (lines.length < 2) {
        throw new Error("CSV looks empty.");
      }
      const rows = lines.slice(1).map((line, index) => {
        const parts = line.split(",").map((p) => p.replace(/^"|"$/g, "").trim());
        return {
          account_code: parts[0] ?? "",
          account_name: parts[1] ?? "",
          debit: parts[2] || "0",
          credit: parts[3] || "0",
          row_index: index + 1,
        };
      });
      setExtract({
        rows,
        method: "pdfplumber_table",
        page_count: 1,
        warnings: ["Loaded from CSV — review before paying."],
        message: "Review and correct the rows, then continue to payment.",
      });
      setStep("review");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed");
    } finally {
      setBusy(false);
    }
  };

  const onConfirm = async (rows: EditableExtractedRow[]) => {
    setBusy(true);
    setError(null);
    try {
      const body = {
        rows: rows.map((row) => ({
          account_code: row.account_code,
          account_name: row.account_name,
          debit: row.debit || "0",
          credit: row.credit || "0",
        })),
        customer_email: email.trim() || null,
      };
      const result = await apiFetch<{
        checkout_url: string;
        session_id: string;
        conversion_id: string;
        amount_eur: string;
      }>("/solutions/convert/checkout", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setStep("redirecting");
      window.location.href = result.checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-6 py-12 sm:px-8">
      <div>
        <p className="text-sm font-medium uppercase tracking-wide text-ink-secondary">
          Solutions · Convert Trial Balance
        </p>
        <h1 className="mt-2 font-display text-3xl tracking-tight text-ink sm:text-4xl">
          Convert trial balance (PDF to Excel)
        </h1>
        <p className="mt-3 max-w-2xl text-base text-ink-secondary">
          Upload a PDF trial balance, review the extracted rows, pay once (€19),
          and download structured Excel. No Kastree account required. General
          ledger conversion is coming later.
        </p>
        <p className="mt-3 text-sm text-ink-secondary">
          Looking for the full Financial Intelligence Platform?{" "}
          <Link
            href="/pricing"
            className="font-medium text-accent underline underline-offset-2"
          >
            See pricing
          </Link>
          {" · "}
          <Link
            href="/"
            className="font-medium text-accent underline underline-offset-2"
          >
            Kastree home
          </Link>
        </p>
      </div>

      {step === "upload" || step === "redirecting" ? (
        <>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            className={`rounded border-2 border-dashed px-6 py-12 text-center ${
              dragOver
                ? "border-accent bg-surface-elevated"
                : "border-line bg-surface-elevated/60"
            }`}
          >
            <p className="text-sm font-medium text-ink">
              Drag and drop a trial balance (.pdf or .csv)
            </p>
            <label className="mt-4 inline-block cursor-pointer rounded bg-accent px-4 py-2 text-sm font-medium text-accent-foreground">
              Choose file
              <input
                type="file"
                accept=".pdf,.csv,application/pdf,text/csv"
                className="hidden"
                onChange={(e) => onPick(e.target.files?.[0] ?? null)}
              />
            </label>
            {file ? (
              <p className="mt-3 text-sm text-ink-secondary">{file.name}</p>
            ) : null}
          </div>

          <label className="block text-sm">
            <span className="mb-1 block text-ink-secondary">
              Email for receipt (optional)
            </span>
            <input
              type="email"
              className="w-full max-w-md rounded border border-line bg-surface-elevated px-3 py-2"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@practice.ie"
            />
          </label>

          {error ? (
            <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </p>
          ) : null}

          <button
            type="button"
            disabled={!file || busy || step === "redirecting"}
            onClick={() => void runExtractOrPreview()}
            className="rounded bg-accent px-4 py-2 text-sm font-medium text-accent-foreground disabled:opacity-50"
          >
            {busy
              ? "Working…"
              : step === "redirecting"
                ? "Redirecting to secure checkout…"
                : "Extract and review"}
          </button>

          <p className="text-xs text-ink-secondary">
            Already a Kastree subscriber? Use the in-app Upload flow — PDF
            extract and statements are included there at no extra charge.
            Convert is a separate one-time tool for visitors without an account.
          </p>
        </>
      ) : null}

      {step === "review" && extract ? (
        <div className="space-y-4">
          <label className="block text-sm">
            <span className="mb-1 block text-ink-secondary">
              Email for receipt (optional)
            </span>
            <input
              type="email"
              className="w-full max-w-md rounded border border-line bg-surface-elevated px-3 py-2"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          {error ? (
            <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </p>
          ) : null}
          <PdfExtractReview
            rows={extract.rows}
            method={extract.method}
            warnings={extract.warnings}
            busy={busy}
            confirmLabel="Confirm and pay €19"
            busyLabel="Starting checkout…"
            onConfirm={onConfirm}
            onCancel={() => {
              setStep("upload");
              setExtract(null);
            }}
          />
          <p className="text-sm text-ink-secondary">
            Confirming continues to Stripe Checkout for a one-time{" "}
            <span className="font-medium text-ink">€19</span> payment. You will
            then download Excel — nothing enters the Kastree mapping pipeline.
          </p>
        </div>
      ) : null}
    </div>
  );
}
