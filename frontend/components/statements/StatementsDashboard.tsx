"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { formatCurrency, formatCurrencyCode } from "@/lib/currency";
import { DISCLAIMER_TEXT } from "@/lib/constants";
import type { StatementBlock, StatementsResponse } from "@/types";
import { ExportButton } from "./ExportButton";

type Tab = "SOPL" | "SOFP" | "SOCIE";

function StatementTable({
  block,
  currencyCode,
}: {
  block: StatementBlock;
  currencyCode: string;
}) {
  return (
    <div className="overflow-x-auto rounded border border-stone-200 bg-white">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-stone-200 bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
          <tr>
            <th className="px-3 py-2 font-medium">Line item</th>
            <th className="px-3 py-2 text-right font-medium">Amount</th>
          </tr>
        </thead>
        <tbody>
          {block.lines.map((line) => {
            const numericAmount = Number.parseFloat(line.amount);
            const isNegative = Number.isFinite(numericAmount) && numericAmount < 0;
            return (
              <tr
                key={line.id}
                className={`border-b border-stone-100 ${line.is_subtotal ? "bg-stone-50" : ""}`}
              >
                <td
                  className={`px-3 py-2 ${line.is_subtotal ? "font-semibold" : ""}`}
                >
                  {line.line_item_name}
                </td>
                <td
                  className={`px-3 py-2 text-right tabular-nums ${line.is_subtotal ? "font-semibold" : ""} ${isNegative ? "text-red-700" : ""}`}
                >
                  {formatCurrency(line.amount, currencyCode)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function StatementsDashboard({ tbId }: { tbId: string }) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("SOPL");

  const statementsQuery = useQuery({
    queryKey: ["tb-statements", tbId],
    queryFn: async () => {
      try {
        return await apiFetch<StatementsResponse>(
          `/trial-balances/${tbId}/statements`,
          { getToken },
        );
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          return null;
        }
        throw err;
      }
    },
  });

  const generateMutation = useMutation({
    mutationFn: () =>
      apiFetch<StatementsResponse>(`/trial-balances/${tbId}/statements`, {
        method: "POST",
        getToken,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["tb-statements", tbId], data);
    },
  });

  const statementsData = statementsQuery.data ?? generateMutation.data ?? null;
  const currencyCode = statementsData?.functional_currency ?? "GBP";

  const block = statementsData?.statements.find((s) => s.statement_type === tab);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Statements</h1>
        <p className="mt-1 text-sm text-stone-600">
          Review SOPL, SOFP, and SOCIE for this trial balance.
        </p>
      </div>

      <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
        <span className="font-medium">Disclaimer: </span>
        {DISCLAIMER_TEXT}
      </p>

      {statementsQuery.isLoading ? (
        <p className="text-sm text-stone-600">Loading statements…</p>
      ) : null}

      {statementsQuery.error ? (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {statementsQuery.error instanceof Error
            ? statementsQuery.error.message
            : "Failed to load statements"}
        </p>
      ) : null}

      {!statementsQuery.isLoading && statementsQuery.data === null ? (
        <div className="space-y-3 rounded border border-stone-200 bg-white p-6">
          <p className="text-sm text-stone-600">
            Statements have not been generated yet for this trial balance.
          </p>
          {generateMutation.error ? (
            <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {generateMutation.error instanceof Error
                ? generateMutation.error.message
                : "Generate failed"}
            </p>
          ) : null}
          <button
            type="button"
            disabled={generateMutation.isPending}
            onClick={() => generateMutation.mutate()}
            className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {generateMutation.isPending
              ? "Generating…"
              : "Generate Statements"}
          </button>
        </div>
      ) : null}

      {statementsData ? (
        <>
          <p className="text-sm text-stone-700">
            All amounts in{" "}
            <span className="font-mono font-medium">
              {formatCurrencyCode(currencyCode)}
            </span>
          </p>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex gap-2 border-b border-stone-200">
              {(["SOPL", "SOFP", "SOCIE"] as Tab[]).map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => setTab(name)}
                  className={`px-3 py-2 text-sm font-medium ${
                    tab === name
                      ? "border-b-2 border-stone-900 text-stone-900"
                      : "text-stone-500 hover:text-stone-800"
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <ExportButton tbId={tbId} />
              {generateMutation.error ? (
                <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                  {generateMutation.error instanceof Error
                    ? generateMutation.error.message
                    : "Regenerate failed"}
                </p>
              ) : null}
              <button
                type="button"
                disabled={generateMutation.isPending}
                onClick={() => generateMutation.mutate()}
                className="rounded border border-stone-300 bg-white px-4 py-2 text-sm font-medium text-stone-900 disabled:opacity-50"
              >
                {generateMutation.isPending
                  ? "Regenerating…"
                  : "Regenerate Statements"}
              </button>
            </div>
          </div>
          {block ? (
            <StatementTable block={block} currencyCode={currencyCode} />
          ) : (
            <p className="text-sm text-stone-600">No {tab} lines returned.</p>
          )}
        </>
      ) : null}
    </div>
  );
}
