"use client";

import { Suspense, type ReactNode } from "react";
import { TbWorkspaceProvider } from "@/components/statements/TbWorkspaceProvider";

/**
 * Shared TB chrome: Dashboard | Statements switcher + persistent Ask panel.
 * Children remount on navigation; this layout (and Ask thread) does not.
 */
export default function TrialBalanceLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: { tbId: string };
}) {
  return (
    <Suspense
      fallback={
        <p className="text-sm text-soft">Loading workspace…</p>
      }
    >
      <TbWorkspaceProvider tbId={params.tbId}>{children}</TbWorkspaceProvider>
    </Suspense>
  );
}
