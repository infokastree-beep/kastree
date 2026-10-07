"use client";

import { sublineGapAccount } from "@/lib/workspace-load-error";

/** Shows an API error unchanged. A sub-line refusal links to that sidebar section. */
export function StatutoryLoadError({
  message,
  testId,
  onReview,
}: {
  message: string;
  testId: string;
  onReview: () => void;
}) {
  const account = sublineGapAccount(message);
  return (
    <p
      className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
      data-testid={testId}
    >
      {message}
      {account !== null ? (
        <>
          {" "}
          <button
            type="button"
            className="font-semibold underline"
            data-testid="statutory-subline-review-link"
            onClick={onReview}
          >
            Sub-line review
          </button>
        </>
      ) : null}
    </p>
  );
}
