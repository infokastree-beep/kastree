"use client";

import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { CANONICAL_LINES } from "@/lib/constants";
import { confidenceBadgeClass, formatConfidence } from "@/lib/utils";
import type {
  MappingConfirmItem,
  MappingConfirmResponse,
  MappingItem,
  MappingResponse,
  StatusResponse,
} from "@/types";

const MAPPING_STATUSES = new Set(["pending", "parsing", "mapping"]);

function isAutoMappingComplete(jobs: StatusResponse["jobs"]): boolean {
  const parse = jobs.find((job) => job.job_type === "parse");
  const map = jobs.find((job) => job.job_type === "map");
  return parse?.status === "complete" && map?.status === "complete";
}

function buildInitialSelections(
  rows: MappingItem[],
  previous: Record<string, string>,
): Record<string, string> {
  const next = { ...previous };
  for (const row of rows) {
    if (!(row.id in next)) {
      next[row.id] = row.suggested_canonical_line;
    }
  }
  return next;
}

export function MappingReview({ tbId }: { tbId: string }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [selections, setSelections] = useState<Record<string, string>>({});
  const selectionsRef = useRef(selections);
  selectionsRef.current = selections;

  const statusQuery = useQuery({
    queryKey: ["tb-status", tbId],
    queryFn: () =>
      apiFetch<StatusResponse>(`/trial-balances/${tbId}/status`, { getToken }),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 1500;
      if (isAutoMappingComplete(data.jobs)) return false;
      if (!MAPPING_STATUSES.has(data.status)) return false;
      return 1500;
    },
  });

  const mappingReady =
    Boolean(statusQuery.data) &&
    (isAutoMappingComplete(statusQuery.data.jobs) ||
      !MAPPING_STATUSES.has(statusQuery.data?.status ?? "pending"));

  const mappingQuery = useQuery({
    queryKey: ["tb-mapping", tbId],
    queryFn: () =>
      apiFetch<MappingResponse>(`/trial-balances/${tbId}/mapping`, { getToken }),
    enabled: mappingReady,
  });

  const sortedMappings = useMemo(() => {
    const rows = mappingQuery.data?.mappings ?? [];
    return [...rows].sort((a, b) => {
      const aUnmapped = a.suggested_canonical_line === "unmapped" ? 0 : 1;
      const bUnmapped = b.suggested_canonical_line === "unmapped" ? 0 : 1;
      if (aUnmapped !== bUnmapped) return aUnmapped - bUnmapped;
      return a.source_name.localeCompare(b.source_name);
    });
  }, [mappingQuery.data?.mappings]);

  useEffect(() => {
    if (!mappingQuery.data) return;
    setSelections((prev) =>
      buildInitialSelections(mappingQuery.data.mappings, prev),
    );
  }, [mappingQuery.data]);

  const selectionsReady = useMemo(
    () =>
      sortedMappings.length > 0 &&
      sortedMappings.every((row) => row.id in selections),
    [sortedMappings, selections],
  );

  const unmappedCount = useMemo(
    () =>
      sortedMappings.filter(
        (row) => (selections[row.id] ?? row.suggested_canonical_line) === "unmapped",
      ).length,
    [sortedMappings, selections],
  );

  const confirmMutation = useMutation({
    mutationFn: async (rows: MappingItem[]) => {
      const currentSelections = selectionsRef.current;
      const mappings: MappingConfirmItem[] = rows.map((row) => {
        const canonical = currentSelections[row.id];
        if (canonical === undefined) {
          throw new Error(`Missing canonical line for ${row.source_name}`);
        }
        return {
          id: row.id,
          canonical_line: canonical,
          is_confirmed: true,
          is_ignored: false,
        };
      });
      return apiFetch<MappingConfirmResponse>(
        `/trial-balances/${tbId}/mapping/confirm`,
        {
          method: "POST",
          getToken,
          body: JSON.stringify({ mappings }),
        },
      );
    },
    onSuccess: () => {
      router.push(`/dashboard/${tbId}`);
    },
  });

  const avgConfidence = useMemo(() => {
    const withConf = sortedMappings.filter(
      (m): m is MappingItem & { confidence: number } => m.confidence !== null,
    );
    if (withConf.length === 0) return null;
    const sum = withConf.reduce((acc, m) => acc + m.confidence, 0);
    return sum / withConf.length;
  }, [sortedMappings]);

  if (statusQuery.isLoading) {
    return <p className="text-sm text-stone-600">Loading trial balance status…</p>;
  }

  if (statusQuery.error) {
    return (
      <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
        {statusQuery.error instanceof Error
          ? statusQuery.error.message
          : "Failed to load status"}
      </p>
    );
  }

  if (statusQuery.data?.status === "failed") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Upload failed</h1>
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {statusQuery.data.error_message ??
            "This trial balance could not be parsed. Check the file format and try uploading again."}
        </p>
        <Link
          href="/upload"
          className="inline-block rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white"
        >
          Back to upload
        </Link>
      </div>
    );
  }

  if (!mappingReady) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">Mapping in progress</h1>
        <p className="text-sm text-stone-600">
          Status: <span className="font-medium">{statusQuery.data?.status}</span>
          {statusQuery.data?.current_step
            ? ` — ${statusQuery.data.current_step}`
            : ""}
        </p>
        <div className="h-2 w-full overflow-hidden rounded bg-stone-200">
          <div
            className="h-full bg-stone-800 transition-all"
            style={{ width: `${statusQuery.data?.progress_pct ?? 0}%` }}
          />
        </div>
        <p className="text-xs text-stone-500">Polling until mapping completes…</p>
      </div>
    );
  }

  if (mappingQuery.isLoading) {
    return <p className="text-sm text-stone-600">Loading mappings…</p>;
  }

  if (mappingQuery.error) {
    return (
      <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
        {mappingQuery.error instanceof Error
          ? mappingQuery.error.message
          : "Failed to load mappings"}
      </p>
    );
  }

  const total = sortedMappings.length;
  const mapped = sortedMappings.filter(
    (m) => (selections[m.id] ?? m.suggested_canonical_line) !== "unmapped",
  ).length;

  if (total === 0) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Review mappings</h1>
        <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          No account rows were found in this trial balance. The file may be empty or
          could not be parsed correctly.
        </p>
        <Link
          href="/upload"
          className="inline-block rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white"
        >
          Upload a different file
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Review mappings</h1>
        <p className="mt-1 text-sm text-stone-600">
          {mapped} of {total} accounts mapped
          {avgConfidence !== null
            ? ` (${Math.round(avgConfidence * 100)}% avg confidence)`
            : ""}
          . Unmapped rows are pinned to the top.
        </p>
      </div>

      <div className="overflow-x-auto rounded border border-stone-200 bg-white">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-3 py-2 font-medium">Code</th>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Canonical line</th>
              <th className="px-3 py-2 font-medium">Confidence</th>
              <th className="px-3 py-2 font-medium">Method</th>
            </tr>
          </thead>
          <tbody>
            {sortedMappings.map((row) => (
              <tr key={row.id} className="border-b border-stone-100">
                <td className="px-3 py-2 font-mono text-xs">
                  {row.source_code ?? "—"}
                </td>
                <td className="px-3 py-2">{row.source_name}</td>
                <td className="px-3 py-2">
                  <select
                    className="w-full min-w-[12rem] rounded border border-stone-300 bg-white px-2 py-1"
                    value={selections[row.id] ?? row.suggested_canonical_line}
                    onChange={(e) =>
                      setSelections((prev) => ({
                        ...prev,
                        [row.id]: e.target.value,
                      }))
                    }
                  >
                    {CANONICAL_LINES.map((line) => (
                      <option key={line} value={line}>
                        {line}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${confidenceBadgeClass(row.confidence)}`}
                  >
                    {formatConfidence(row.confidence)}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <span className="rounded bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-700">
                    {row.method}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {confirmMutation.error ? (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {confirmMutation.error instanceof Error
            ? confirmMutation.error.message
            : "Confirm failed"}
        </p>
      ) : null}

      {unmappedCount > 0 ? (
        <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {unmappedCount} account{unmappedCount === 1 ? "" : "s"} still unmapped.
          Choose a canonical line for every row before confirming.
        </p>
      ) : null}

      <button
        type="button"
        disabled={
          confirmMutation.isPending ||
          total === 0 ||
          !selectionsReady ||
          unmappedCount > 0
        }
        onClick={() => confirmMutation.mutate(sortedMappings)}
        className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {confirmMutation.isPending ? "Confirming…" : "Confirm Mappings"}
      </button>
    </div>
  );
}
