"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { MarketingFooter } from "@/components/landing/MarketingFooter";
import { MarketingNav } from "@/components/landing/MarketingNav";
import { apiFetch, getApiBaseUrl } from "@/lib/api";

type Status = {
  conversion_id: string;
  status: string;
  paid: boolean;
  download_ready: boolean;
};

export function ConvertSuccessClient() {
  const params = useSearchParams();
  const sessionId = params.get("session_id") ?? "";
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [polling, setPolling] = useState(true);

  useEffect(() => {
    if (!sessionId) {
      setError("Missing checkout session.");
      setPolling(false);
      return;
    }
    let cancelled = false;
    let attempts = 0;

    const tick = async () => {
      try {
        const data = await apiFetch<Status>(
          `/solutions/convert/status?session_id=${encodeURIComponent(sessionId)}`,
        );
        if (cancelled) return;
        setStatus(data);
        if (data.paid) {
          setPolling(false);
          return;
        }
        attempts += 1;
        if (attempts < 30) {
          window.setTimeout(() => void tick(), 2000);
        } else {
          setPolling(false);
          setError(
            "Payment is still processing. Refresh this page in a moment, or check your email receipt.",
          );
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Could not verify payment");
        setPolling(false);
      }
    };

    void tick();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const downloadHref = sessionId
    ? `${getApiBaseUrl()}/solutions/convert/download?session_id=${encodeURIComponent(sessionId)}`
    : null;

  return (
    <div className="min-h-screen bg-surface text-ink">
      <MarketingNav />
      <main className="mx-auto max-w-xl space-y-6 px-6 py-16 sm:px-8">
        <h1 className="font-display text-3xl tracking-tight">Payment received</h1>
        {polling ? (
          <p className="text-ink-secondary">Confirming your payment…</p>
        ) : null}
        {error ? (
          <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
            {error}
          </p>
        ) : null}
        {status?.paid && downloadHref ? (
          <div className="space-y-4">
            <p className="text-ink-secondary">
              Your trial balance is ready. Download the Excel file below.
            </p>
            <a
              href={downloadHref}
              className="inline-block rounded bg-accent px-4 py-2 text-sm font-medium text-accent-foreground"
            >
              Download Excel
            </a>
            <div className="rounded border border-line bg-surface-elevated px-4 py-4 text-sm text-ink-secondary">
              <p>
                Want this to go straight into full statements, variance, and AI
                commentary?{" "}
                <Link
                  href="/sign-up"
                  className="font-medium text-accent underline underline-offset-2"
                >
                  Create a free Kastree account
                </Link>
                .
              </p>
            </div>
          </div>
        ) : null}
        <p className="text-sm">
          <Link href="/solutions/convert" className="underline">
            Convert another trial balance
          </Link>
        </p>
      </main>
      <MarketingFooter />
    </div>
  );
}
