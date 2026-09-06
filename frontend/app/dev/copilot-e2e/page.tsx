"use client";

/**
 * Local live E2E harness for Copilot UI (Phase 3).
 * Clerk is bypassed; paste a session JWT into sessionStorage.e2e_token.
 * Not linked from product nav.
 */

import { useEffect, useState } from "react";
import {
  CopilotPanel,
  type CopilotNavigateTarget,
} from "@/components/statements/CopilotPanel";

const BERKSHIRE_TB_ID = "fd2e4bf4-773c-4c7c-adbe-b3cb78dda028";

export default function CopilotE2EPage() {
  const [ready, setReady] = useState(false);
  const [tokenPresent, setTokenPresent] = useState(false);

  useEffect(() => {
    setTokenPresent(Boolean(sessionStorage.getItem("e2e_token")));
    setReady(true);
  }, []);

  return (
    <div className="min-h-screen bg-surface p-6">
      <h1 className="font-display text-2xl font-semibold text-ink">
        Copilot E2E harness
      </h1>
      <p className="mt-2 max-w-2xl text-sm text-ink-secondary">
        Berkshire TB {BERKSHIRE_TB_ID}. Uses the real CopilotPanel against the
        configured API. Set <code>sessionStorage.e2e_token</code> to a Clerk
        session JWT first.
      </p>
      <p className="mt-2 text-sm" data-testid="e2e-token-status">
        Token: {ready ? (tokenPresent ? "present" : "missing") : "checking…"}
      </p>
      {ready ? (
        <CopilotPanel
          tbId={BERKSHIRE_TB_ID}
          open
          onClose={() => undefined}
          onNavigateCitation={(target: CopilotNavigateTarget) => {
            const el = document.getElementById(target.anchorId);
            el?.scrollIntoView({ behavior: "smooth", block: "center" });
          }}
          getTokenOverride={async () => sessionStorage.getItem("e2e_token")}
        />
      ) : null}
    </div>
  );
}
