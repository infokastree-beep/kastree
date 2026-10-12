"use client";

import {
  AUDIT_EXEMPTION_NOTE,
  AUDIT_EXEMPTION_PARAGRAPHS,
  AUDIT_EXEMPTION_PROVISION,
  AUDIT_EXEMPTION_SOURCE,
  AUDIT_EXEMPTION_SOURCE_LABEL,
} from "@/lib/audit-exemption";

export function AuditExemptionClaim({
  claimed,
  canRecord,
  busy,
  positionMessage,
  noticeMessage,
  error,
  onRecord,
}: {
  claimed: boolean | null;
  canRecord: boolean;
  busy: boolean;
  positionMessage: string | null;
  noticeMessage: string | null;
  error: string | null;
  onRecord: (claimed: boolean | null) => void;
}) {
  const position =
    claimed === true
      ? "Audit exemption claimed"
      : claimed === false
        ? "Not claimed"
        : "Not recorded";

  return (
    <section
      id="audit-exemption-claim"
      className="mt-4 space-y-3 rounded-md border border-line bg-surface-elevated p-4"
      data-testid="audit-exemption-claim"
    >
      <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
        Audit exemption
      </h3>
      <p className="text-sm font-semibold text-ink" data-testid="audit-exemption-source">
        {AUDIT_EXEMPTION_SOURCE_LABEL}
      </p>
      <p className="text-sm text-ink-secondary" data-testid="audit-exemption-provision">
        {AUDIT_EXEMPTION_SOURCE}. {AUDIT_EXEMPTION_PROVISION}
      </p>
      <div data-testid="audit-exemption-statement">
        {AUDIT_EXEMPTION_PARAGRAPHS.map((paragraph) => (
          <p key={paragraph} className="text-sm text-ink-secondary">
            {paragraph}
          </p>
        ))}
      </div>
      <p className="text-sm text-ink-secondary" data-testid="audit-exemption-note">
        {AUDIT_EXEMPTION_NOTE}
      </p>
      <p className="text-sm text-ink" data-testid="audit-exemption-position">
        {position}
      </p>
      {positionMessage ? (
        <p className="text-sm text-ink" data-testid="audit-exemption-message">
          {positionMessage}
        </p>
      ) : null}
      {noticeMessage ? (
        <p className="text-sm text-ink" data-testid="audit-exemption-notice">
          {noticeMessage}
        </p>
      ) : null}
      {canRecord ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            data-testid="audit-exemption-claimed"
            disabled={busy}
            className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
            onClick={() => onRecord(true)}
          >
            Audit exemption claimed
          </button>
          <button
            type="button"
            data-testid="audit-exemption-not-claimed"
            disabled={busy}
            className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
            onClick={() => onRecord(false)}
          >
            Not claimed
          </button>
          <button
            type="button"
            data-testid="audit-exemption-clear"
            disabled={busy}
            className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
            onClick={() => onRecord(null)}
          >
            Clear
          </button>
        </div>
      ) : null}
      {error ? (
        <p className="text-sm text-critical" data-testid="audit-exemption-error">
          {error}
        </p>
      ) : null}
    </section>
  );
}
