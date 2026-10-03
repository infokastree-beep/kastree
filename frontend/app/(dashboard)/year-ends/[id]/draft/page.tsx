"use client";

import { Suspense } from "react";
import { StatutoryDraftWorkspace } from "@/components/statutory/StatutoryDraftWorkspace";

/** Persistent statutory workspace for one year end. The address is the return path. */
export default function YearEndDraftPage({
  params,
}: {
  params: { id: string };
}) {
  return (
    <Suspense fallback={<p className="text-sm text-soft">Loading the statutory workspace…</p>}>
      <StatutoryDraftWorkspace yearEndId={params.id} />
    </Suspense>
  );
}
