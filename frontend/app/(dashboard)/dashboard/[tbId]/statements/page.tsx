"use client";

import { Suspense } from "react";
import { StatementsDashboard } from "@/components/statements/StatementsDashboard";

/** Statements workspace — SOPL/SOFP/SOCIE/Variance/Risk (default post-generate landing). */
export default function StatementsPage({
  params,
}: {
  params: { tbId: string };
}) {
  return (
    <Suspense fallback={<p className="text-sm text-soft">Loading statements…</p>}>
      <StatementsDashboard tbId={params.tbId} />
    </Suspense>
  );
}
