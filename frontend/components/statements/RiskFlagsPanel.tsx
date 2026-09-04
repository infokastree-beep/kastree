"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { formatCanonicalLineLabel } from "@/lib/utils";
import type { RiskFlagsResponse, RiskSeverity } from "@/types";

function severityClass(severity: RiskSeverity): string {
  return severity === "critical"
    ? "bg-red-100 text-red-900"
    : "bg-amber-100 text-amber-950";
}

function ruleLabel(ruleName: string): string {
  return formatCanonicalLineLabel(ruleName);
}

export function RiskFlagsPanel({ tbId }: { tbId: string }) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  const riskQuery = useQuery({
    queryKey: ["tb-risk", tbId],
    queryFn: () =>
      apiFetch<RiskFlagsResponse>(`/trial-balances/${tbId}/risk`, {
        getToken,
      }),
  });

  const generateMutation = useMutation({
    mutationFn: () =>
      apiFetch<RiskFlagsResponse>(`/trial-balances/${tbId}/risk`, {
        method: "POST",
        getToken,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["tb-risk", tbId], data);
    },
  });

  const data = generateMutation.data ?? riskQuery.data;
  const flags = data?.flags ?? [];
  const ranThisSession = generateMutation.isSuccess;

  if (riskQuery.isLoading && !generateMutation.data) {
    return <p className="text-sm text-soft">Loading risk flags…</p>;
  }

  if (riskQuery.error && !generateMutation.data) {
    return (
      <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        {riskQuery.error instanceof Error
          ? riskQuery.error.message
          : "Failed to load risk flags"}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-secondary">
          Deterministic rules evaluated against this trial balance
          {flags.length > 0
            ? ` · ${flags.length} flag${flags.length === 1 ? "" : "s"}`
            : ""}
          .
        </p>
        <button
          type="button"
          disabled={generateMutation.isPending}
          onClick={() => generateMutation.mutate()}
          className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
        >
          {generateMutation.isPending
            ? "Running…"
            : flags.length > 0 || ranThisSession
              ? "Refresh risk flags"
              : "Run risk analysis"}
        </button>
      </div>

      {generateMutation.error ? (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {generateMutation.error instanceof Error
            ? generateMutation.error.message
            : "Risk analysis failed"}
        </p>
      ) : null}

      {flags.length === 0 ? (
        <div className="rounded-md border border-line bg-surface-elevated p-6">
          <p className="text-sm text-ink-secondary">
            {ranThisSession
              ? "No risk flags were raised for this trial balance."
              : flags.length === 0 && riskQuery.isSuccess
                ? "No risk flags on file yet. Run risk analysis to evaluate this trial balance."
                : "Risk analysis has not been run yet for this trial balance."}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border border-line bg-surface-elevated">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-line bg-accent-muted/50 text-xs uppercase tracking-[0.12em] text-soft">
              <tr>
                <th className="px-4 py-3 font-semibold">Rule</th>
                <th className="px-4 py-3 font-semibold">Severity</th>
                <th className="px-4 py-3 font-semibold">Description</th>
              </tr>
            </thead>
            <tbody>
              {flags.map((flag) => (
                <tr
                  key={flag.id}
                  className={`border-b border-line/70 ${
                    flag.severity === "critical"
                      ? "bg-red-50/60"
                      : "bg-surface-elevated"
                  }`}
                >
                  <td className="px-4 py-3 align-top font-medium text-ink">
                    {ruleLabel(flag.rule_name)}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <span
                      className={`rounded-md px-2 py-0.5 text-xs font-semibold capitalize ${severityClass(
                        flag.severity,
                      )}`}
                    >
                      {flag.severity}
                    </span>
                  </td>
                  <td className="px-4 py-3 align-top text-ink-secondary">
                    <p>{flag.description}</p>
                    {flag.recommended_action ? (
                      <p className="mt-1.5 text-xs text-soft">
                        <span className="font-semibold text-ink-secondary">
                          Action:{" "}
                        </span>
                        {flag.recommended_action}
                      </p>
                    ) : null}
                    {flag.affected_accounts &&
                    flag.affected_accounts.length > 0 ? (
                      <p className="mt-1.5 text-xs text-soft">
                        Affected:{" "}
                        {flag.affected_accounts
                          .map(
                            (account) =>
                              `${account.account_code} ${account.account_name}`,
                          )
                          .join("; ")}
                      </p>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
