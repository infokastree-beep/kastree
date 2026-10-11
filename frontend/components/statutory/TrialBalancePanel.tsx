"use client";

import Link from "next/link";
import {
  FACE_DATES_SENTENCE,
  FILE_NAME_NOT_RECORDED,
  NO_TRIAL_BALANCE_SELECTED,
  formatPeriodDate,
  formatUploadedAt,
  statementsHref,
  type TrialBalancePage,
} from "@/lib/trial-balance-page";

function recorded(value: string | null, format?: (value: string) => string): string {
  if (value == null || value === "") return "Not recorded";
  return format ? format(value) : value;
}

export function TrialBalancePanel({ page }: { page: TrialBalancePage }) {
  if (page.trial_balance_id == null) {
    return (
      <section className="space-y-3" data-testid="statutory-trial-balance">
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
          Trial balance
        </h2>
        <p className="text-sm text-ink" data-testid="statutory-trial-balance-empty">
          {NO_TRIAL_BALANCE_SELECTED}
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-4" data-testid="statutory-trial-balance">
      <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
        Trial balance
      </h2>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-ink-secondary">Period start</dt>
          <dd className="text-ink" data-testid="statutory-trial-balance-start">
            {recorded(page.period_start, formatPeriodDate)}
          </dd>
        </div>
        <div>
          <dt className="text-ink-secondary">Period end</dt>
          <dd className="text-ink" data-testid="statutory-trial-balance-end">
            {recorded(page.period_end, formatPeriodDate)}
          </dd>
        </div>
        <div>
          <dt className="text-ink-secondary">File name</dt>
          <dd className="text-ink" data-testid="statutory-trial-balance-file">
            {page.file_name ?? FILE_NAME_NOT_RECORDED}
          </dd>
        </div>
        <div>
          <dt className="text-ink-secondary">Uploaded</dt>
          <dd className="text-ink" data-testid="statutory-trial-balance-uploaded">
            {recorded(page.uploaded_at, formatUploadedAt)}
          </dd>
        </div>
        <div>
          <dt className="text-ink-secondary">Accounts</dt>
          <dd className="text-ink" data-testid="statutory-trial-balance-accounts">
            {page.account_count ?? "Not recorded"}
          </dd>
        </div>
        <div>
          <dt className="text-ink-secondary">Currency</dt>
          <dd className="text-ink" data-testid="statutory-trial-balance-currency">
            {recorded(page.currency)}
          </dd>
        </div>
      </dl>
      <p className="text-sm text-ink-secondary" data-testid="statutory-trial-balance-face-dates">
        {FACE_DATES_SENTENCE}
      </p>
      <Link
        href={statementsHref(page.trial_balance_id)}
        className="text-sm font-medium text-accent underline-offset-2 hover:underline"
        data-testid="statutory-trial-balance-statements"
      >
        Open in Statements
      </Link>
    </section>
  );
}
