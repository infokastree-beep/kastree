"use client";

import { StatutoryDraftWorkspace } from "@/components/statutory/StatutoryDraftWorkspace";

/** Persistent statutory workspace for one year end. The address is the return path. */
export default function YearEndDraftPage({
  params,
}: {
  params: { id: string };
}) {
  return <StatutoryDraftWorkspace yearEndId={params.id} />;
}
