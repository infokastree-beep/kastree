"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";

type SublineRow = {
  nominal_code: string;
  account_name: string;
  product1_line: string;
  suggested_line: string | null;
  suggestion_confidence: string | null;
  statutory_line: string | null;
  choices: string[];
};

type SublineReview = {
  blocked: boolean;
  rows: SublineRow[];
};

const LABELS: Record<string, string> = {
  FA_LAND_BUILDINGS: "Land and buildings",
  FA_PLANT_COST: "Plant and machinery",
  FA_FIXTURES_COST: "Fixtures and fittings",
  FA_MOTOR_COST: "Motor vehicles",
  FA_ACCUM_DEP: "Accumulated depreciation",
  ROU_ASSETS: "Right-of-use asset",
  DISTRIBUTION_COSTS: "Distribution costs",
  ADMIN_EXPENSES: "Administrative expenses",
  LOANS_LT1Y: "Loans within one year",
  LOANS_GT1Y: "Loans after more than one year",
  BANK_OVERDRAFT: "Bank overdraft",
  DIRECTOR_LOAN: "Director's loan",
  LEASE_LIABILITY_LT1Y: "Lease liability within one year",
  LEASE_LIABILITY_GT1Y: "Lease liability after more than one year",
  TAX_CHARGE: "Tax charge",
  CORP_TAX: "Corporation tax creditor",
  DEFERRED_TAX: "Deferred tax",
  VAT_CONTROL: "VAT",
  PAYE_PRSI: "PAYE / PRSI",
  DEPRECIATION_CHARGE: "Depreciation charge",
  AMORTISATION_CHARGE: "Amortisation charge",
  FA_INTANGIBLE_COST: "Intangible asset cost",
  FA_INTANGIBLE_AMORT: "Accumulated amortisation",
};

function rowKey(row: SublineRow): string {
  return `${row.nominal_code}\u0000${row.account_name}`;
}

function labelFor(line: string): string {
  return LABELS[line] ?? line;
}

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong";
}

export function StatutorySublineReview({
  yearEndId,
  onConfirmed,
}: {
  yearEndId: string;
  onConfirmed: () => Promise<void>;
}) {
  const { getToken, isSignedIn } = useAuth();
  const queryClient = useQueryClient();
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const reviewQuery = useQuery({
    queryKey: ["statutory-sublines", yearEndId],
    queryFn: () =>
      apiFetch<SublineReview>(
        `/year-ends/${yearEndId}/adopted-trial-balance/sub-lines`,
        { getToken },
      ),
    enabled: isSignedIn,
  });

  useEffect(() => {
    const rows = reviewQuery.data?.rows;
    if (!rows) {
      return;
    }
    setSelections(
      Object.fromEntries(
        rows.map((row) => [
          rowKey(row),
          row.statutory_line ?? row.suggested_line ?? "",
        ]),
      ),
    );
  }, [reviewQuery.data]);

  if (reviewQuery.isLoading) {
    return null;
  }
  if (reviewQuery.error) {
    return (
      <p className="text-sm text-red-800">{messageFrom(reviewQuery.error)}</p>
    );
  }
  const review = reviewQuery.data;
  if (!review || review.rows.length === 0) {
    return null;
  }
  const showsPooledDepreciation = review.rows.some(
    (row) =>
      row.suggested_line === "FA_ACCUM_DEP" ||
      selections[rowKey(row)] === "FA_ACCUM_DEP",
  );

  async function confirm(): Promise<void> {
    if (!review) {
      return;
    }
    const lines = review.rows.flatMap((row) => {
      const statutoryLine = selections[rowKey(row)] ?? "";
      if (!statutoryLine) {
        return [];
      }
      return [
        {
          nominal_code: row.nominal_code,
          account_name: row.account_name,
          statutory_line: statutoryLine,
        },
      ];
    });
    if (lines.length === 0) {
      setError("Choose a statutory sub-line for each account before the draft can be built.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await apiFetch<SublineReview>(
        `/year-ends/${yearEndId}/adopted-trial-balance/sub-lines`,
        {
          method: "POST",
          getToken,
          body: JSON.stringify({ lines }),
        },
      );
      await queryClient.invalidateQueries({
        queryKey: ["statutory-sublines", yearEndId],
      });
      await onConfirmed();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="space-y-3 rounded-md border border-line bg-surface-elevated px-4 py-4"
      data-testid="statutory-sublines"
    >
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
          Statutory sub-lines
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-secondary">
          These accounts need a statutory line before the draft can be built.
          A suggestion is pre-filled and stays changeable. Nothing is posted
          until you confirm it.
        </p>
      </div>
      {review.blocked ? (
        <p className="text-sm text-amber-900" data-testid="statutory-sublines-blocked">
          The draft stays blocked until every row has a confirmed sub-line.
        </p>
      ) : (
        <p className="text-sm text-ink-secondary">Every sub-line is confirmed.</p>
      )}
      {showsPooledDepreciation ? (
        <p className="text-sm text-ink-secondary">
          Accumulated depreciation is one pooled line. The fixed-asset note
          cannot split that pool by class from this mapping.
        </p>
      ) : null}
      {error ? <p className="text-sm text-red-800">{error}</p> : null}
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-line text-xs uppercase tracking-[0.12em] text-soft">
            <tr>
              <th className="px-2 py-2 font-semibold">Account</th>
              <th className="px-2 py-2 font-semibold">Product 1 line</th>
              <th className="px-2 py-2 font-semibold">Suggestion</th>
              <th className="px-2 py-2 font-semibold">Statutory line</th>
            </tr>
          </thead>
          <tbody>
            {review.rows.map((row) => {
              const key = rowKey(row);
              const confidence = row.statutory_line
                ? "Confirmed"
                : row.suggestion_confidence
                  ? `Suggested ${row.suggestion_confidence}`
                  : "Needs review";
              return (
                <tr key={key} className="border-b border-line/70">
                  <td className="px-2 py-2">
                    {row.nominal_code} {row.account_name}
                  </td>
                  <td className="px-2 py-2">{row.product1_line}</td>
                  <td className="px-2 py-2">{confidence}</td>
                  <td className="px-2 py-2">
                    <select
                      aria-label={`Statutory line for ${row.account_name}`}
                      className="w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
                      value={selections[key] ?? ""}
                      disabled={busy}
                      onChange={(event) =>
                        setSelections((current) => ({
                          ...current,
                          [key]: event.target.value,
                        }))
                      }
                    >
                      <option value="">Choose a line</option>
                      {row.choices.map((choice) => (
                        <option key={choice} value={choice}>
                          {labelFor(choice)}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        data-testid="statutory-sublines-confirm"
        disabled={busy}
        onClick={() => void confirm()}
        className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground disabled:opacity-50"
      >
        {busy ? "Saving…" : "Confirm sub-lines"}
      </button>
    </section>
  );
}
