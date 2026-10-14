"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";

type DraftRow = {
  draft_id: string;
  version_number: number;
  status: string;
  locked: boolean;
  frozen: boolean;
};

type DraftListPage = {
  year_end_id: string;
  drafts: DraftRow[];
};

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "The draft list could not be loaded.";
}

function marks(row: DraftRow): string {
  const parts: string[] = [];
  if (row.locked) {
    parts.push("Locked");
  }
  if (row.frozen) {
    parts.push("Frozen");
  }
  return parts.length > 0 ? parts.join(", ") : "—";
}

export function DraftList({ yearEndId }: { yearEndId: string }) {
  const { getToken } = useAuth();
  const page = useQuery({
    queryKey: ["draft-list", yearEndId],
    queryFn: () =>
      apiFetch<DraftListPage>(`/year-ends/${yearEndId}/drafts`, { getToken }),
  });

  if (page.isLoading) {
    return <p className="text-sm text-soft">Loading draft versions…</p>;
  }
  if (page.error || !page.data) {
    return (
      <p className="text-sm text-red-800" data-testid="draft-list-error">
        {messageFrom(page.error)}
      </p>
    );
  }
  const rows = page.data.drafts;

  return (
    <section className="space-y-4" data-testid="draft-list">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold text-ink">Draft list</h2>
        <p className="text-sm text-ink-secondary">
          Versions for this year end. Opening a draft stays on the workspace.
        </p>
      </header>
      {rows.length === 0 ? (
        <p className="text-sm text-ink">This year end has no draft versions yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-line text-xs uppercase tracking-wide text-soft">
              <tr>
                <th className="px-2 py-2 font-medium">Version</th>
                <th className="px-2 py-2 font-medium">Status</th>
                <th className="px-2 py-2 font-medium">Locked or frozen</th>
                <th className="px-2 py-2 font-medium">Open</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.draft_id} className="border-b border-line">
                  <td className="px-2 py-2">{row.version_number}</td>
                  <td className="px-2 py-2">{row.status}</td>
                  <td className="px-2 py-2">{marks(row)}</td>
                  <td className="px-2 py-2">
                    <Link
                      href={`/year-ends/${yearEndId}/draft?section=review`}
                      className="font-medium text-ink underline"
                    >
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
