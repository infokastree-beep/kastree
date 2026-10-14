"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";

type Line = { canonical_line: string; amount: string };

type Difference = {
  account_code: string;
  account_name: string;
  previous_line: string;
  current_line: string;
};

type Source = {
  kind: string;
  preferred: boolean;
  available: boolean;
  refusal: string | null;
  guidance: string | null;
  lines: Line[];
  mapping_differences: Difference[];
  checks: { code: string; passed: boolean | null; message: string }[];
};

type PriorYearPage = {
  prior_year_validated: boolean;
  first_financial_period: boolean;
  comparative_source: string | null;
  stored_lines: Line[];
  stale_notice: string | null;
  face_date_notice: string | null;
  sources: Source[];
};

const FIELD =
  "rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink disabled:opacity-50";

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "The prior-year page could not be loaded.";
}

export function PriorYearComparatives({
  yearEndId,
  canPrepare,
}: {
  yearEndId: string;
  canPrepare: boolean;
}) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const page = useQuery({
    queryKey: ["prior-year", yearEndId],
    queryFn: () =>
      apiFetch<PriorYearPage>(`/year-ends/${yearEndId}/prior-year`, { getToken }),
  });
  const [manualLines, setManualLines] = useState<Line[]>([
    { canonical_line: "", amount: "" },
  ]);
  const [matchesFiled, setMatchesFiled] = useState(false);
  const [mappingConfirmed, setMappingConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["prior-year", yearEndId] });
    await queryClient.invalidateQueries({ queryKey: ["year-end", yearEndId] });
  }

  async function post(path: string, body: unknown): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/year-ends/${yearEndId}${path}`, {
        method: "POST",
        getToken,
        body: JSON.stringify(body),
      });
      await refresh();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  if (page.isLoading) {
    return <p className="text-sm text-soft">Loading prior-year comparatives…</p>;
  }
  if (page.error || !page.data) {
    return (
      <p className="text-sm text-red-800" data-testid="prior-year-error">
        {messageFrom(page.error)}
      </p>
    );
  }
  const data = page.data;
  const trial = data.sources.find((source) => source.kind === "product1_tb");
  const first = data.sources.find((source) => source.kind === "first_period");
  const manual = data.sources.find((source) => source.kind === "manual");
  const finalSource = data.sources.find((source) => source.kind === "final_snapshot");
  const differences = trial?.mapping_differences ?? [];

  return (
    <section className="space-y-6" data-testid="prior-year-comparatives">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold text-ink">Prior-year comparatives</h2>
        <p className="text-sm text-ink-secondary">
          The first source that can be used is preferred. Confirming stores a
          snapshot. A later change to the source does not move the printed column.
        </p>
      </header>
      {data.stale_notice ? (
        <p className="text-sm text-ink" data-testid="prior-year-stale">
          {data.stale_notice}
        </p>
      ) : null}
      {data.face_date_notice ? (
        <p className="text-sm text-ink" data-testid="prior-year-face-dates">
          {data.face_date_notice}
        </p>
      ) : null}
      {data.stored_lines.length > 0 ? (
        <ul className="text-sm text-ink" data-testid="prior-year-stored">
          {data.stored_lines.map((line) => (
            <li key={line.canonical_line}>
              {line.canonical_line} {line.amount}
            </li>
          ))}
        </ul>
      ) : null}
      {data.first_financial_period ? (
        <p className="text-sm text-ink" data-testid="prior-year-first-statement">
          This is the company&apos;s first financial period. Comparative amounts
          are not presented.
        </p>
      ) : null}
      {error ? (
        <p className="text-sm text-red-800" data-testid="prior-year-save-error">
          {error}
        </p>
      ) : null}

      <article className="space-y-3" data-testid="prior-year-source-trial-balance">
        <h3 className="font-medium text-ink">
          Previous trial balance
          {trial?.preferred ? " (preferred)" : ""}
        </h3>
        {trial?.refusal ? <p className="text-sm text-ink">{trial.refusal}</p> : null}
        {trial?.available ? (
          <>
            <ul className="text-sm text-ink">
              {trial.lines.map((line) => (
                <li key={line.canonical_line}>
                  {line.canonical_line} {line.amount}
                </li>
              ))}
            </ul>
            {differences.length > 0 ? (
              <div className="space-y-2">
                <p className="text-sm text-ink">
                  These accounts are mapped to a different line from the previous
                  period&apos;s statements.
                </p>
                <ul data-testid="prior-year-mapping-differences">
                  {differences.map((row) => (
                    <li key={`${row.account_code}-${row.account_name}`}>
                      {row.account_code} {row.account_name}: {row.previous_line} to{" "}
                      {row.current_line}
                    </li>
                  ))}
                </ul>
                <label className="flex items-center gap-2 text-sm text-ink">
                  <input
                    type="checkbox"
                    checked={mappingConfirmed}
                    disabled={!canPrepare || busy}
                    onChange={(event) => setMappingConfirmed(event.target.checked)}
                  />
                  Confirm the accounts whose mapping differs
                </label>
              </div>
            ) : null}
            {canPrepare ? (
              <button
                type="button"
                className="rounded-md bg-ink px-3 py-2 text-sm text-surface disabled:opacity-50"
                disabled={busy || (differences.length > 0 && !mappingConfirmed)}
                onClick={() =>
                  void post("/prior-year/from-trial-balance", {
                    confirm: true,
                    mapping_differences_confirmed: mappingConfirmed,
                  })
                }
              >
                Confirm the prior trial balance
              </button>
            ) : null}
          </>
        ) : null}
      </article>

      <article className="space-y-3" data-testid="prior-year-source-first-period">
        <h3 className="font-medium text-ink">
          First financial period
          {first?.preferred ? " (preferred)" : ""}
        </h3>
        <p className="text-sm text-ink-secondary">{first?.guidance}</p>
        {first?.refusal ? <p className="text-sm text-ink">{first.refusal}</p> : null}
        {canPrepare && first?.available && !data.first_financial_period ? (
          <button
            type="button"
            className="rounded-md bg-ink px-3 py-2 text-sm text-surface disabled:opacity-50"
            disabled={busy}
            onClick={() => void post("/first-financial-period", {})}
          >
            Mark this as the first financial period
          </button>
        ) : null}
        {canPrepare && data.first_financial_period ? (
          <button
            type="button"
            className="rounded-md border border-line px-3 py-2 text-sm text-ink disabled:opacity-50"
            disabled={busy}
            data-testid="prior-year-undo"
            onClick={() => void post("/first-financial-period/undo", {})}
          >
            Undo the first financial period
          </button>
        ) : null}
      </article>

      <article className="space-y-3" data-testid="prior-year-source-manual">
        <h3 className="font-medium text-ink">
          Manual entry
          {manual?.preferred ? " (preferred)" : ""}
        </h3>
        {manual?.refusal ? <p className="text-sm text-ink">{manual.refusal}</p> : null}
        <ul className="text-sm text-ink-secondary">
          {(manual?.checks ?? []).map((check) => (
            <li key={check.code}>{check.message}</li>
          ))}
        </ul>
        {manual?.available && canPrepare ? (
          <>
            {manualLines.map((line, index) => (
              <div key={index} className="flex gap-2">
                <input
                  className={FIELD}
                  aria-label="Canonical line"
                  value={line.canonical_line}
                  onChange={(event) =>
                    setManualLines((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index
                          ? { ...item, canonical_line: event.target.value }
                          : item,
                      ),
                    )
                  }
                />
                <input
                  className={FIELD}
                  aria-label="Amount"
                  value={line.amount}
                  onChange={(event) =>
                    setManualLines((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index
                          ? { ...item, amount: event.target.value }
                          : item,
                      ),
                    )
                  }
                />
              </div>
            ))}
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={matchesFiled}
                disabled={busy}
                onChange={(event) => setMatchesFiled(event.target.checked)}
              />
              matches last year&apos;s filed accounts
            </label>
            <button
              type="button"
              className="rounded-md bg-ink px-3 py-2 text-sm text-surface disabled:opacity-50"
              disabled={busy || !matchesFiled}
              onClick={() =>
                void post("/prior-year", {
                  matches_filed_accounts: true,
                  lines: manualLines.filter(
                    (line) => line.canonical_line.trim() && line.amount.trim(),
                  ),
                })
              }
            >
              Confirm manual comparatives
            </button>
          </>
        ) : null}
      </article>

      <article className="space-y-3" data-testid="prior-year-source-final">
        <h3 className="font-medium text-ink">
          Previous final snapshot
          {finalSource?.preferred ? " (preferred)" : ""}
        </h3>
        {finalSource?.refusal && !finalSource.available ? (
          <p className="text-sm text-ink">{finalSource.refusal}</p>
        ) : null}
        {finalSource?.available ? (
          <ul className="text-sm text-ink">
            {finalSource.lines.map((line) => (
              <li key={line.canonical_line}>
                {line.canonical_line} {line.amount}
              </li>
            ))}
          </ul>
        ) : null}
        {canPrepare && finalSource?.available ? (
          <button
            type="button"
            className="rounded-md bg-ink px-3 py-2 text-sm text-surface disabled:opacity-50"
            disabled={busy}
            onClick={() => void post("/prior-year/from-final", { confirm: true })}
          >
            Copy the previous final snapshot
          </button>
        ) : null}
      </article>
    </section>
  );
}
