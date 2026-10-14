import type { ReactNode } from "react";
import Link from "next/link";

import {
  checkLine,
  fixHref,
  groupFailedChecks,
  presentCheck,
  severityTag,
  type ReviewCheck,
} from "@/lib/dashboard-groups";

export function ReviewChecks({
  yearEndId,
  checks,
  unansweredCount,
  renderExtra,
}: {
  yearEndId: string;
  checks: readonly ReviewCheck[];
  unansweredCount: number;
  renderExtra?: (check: ReviewCheck) => ReactNode;
}) {
  const groups = groupFailedChecks(checks);
  if (groups.length === 0) {
    return null;
  }
  return (
    <div className="mt-3 space-y-4" data-testid="statutory-review-groups">
      {groups.map((group) => (
        <section key={group.area}>
          <h3 className="text-sm font-semibold">{group.area}</h3>
          <ul className="mt-1 space-y-2 text-sm">
            {group.checks.map((check, index) => {
              const fix = presentCheck(check).fix;
              return (
                <li key={`${check.code}-${index}`}>
                  <span
                    className="mr-2 inline-flex rounded-full border border-line px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]"
                    data-testid={`statutory-severity-${check.code}`}
                  >
                    {severityTag(check)}
                  </span>
                  <span>{checkLine(check, unansweredCount)}</span>{" "}
                  <Link
                    href={fixHref(yearEndId, fix)}
                    className="font-semibold underline"
                    data-testid={`statutory-fix-${check.code}`}
                  >
                    Fix
                  </Link>
                  {renderExtra ? renderExtra(check) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
