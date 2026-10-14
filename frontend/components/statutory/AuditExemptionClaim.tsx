"use client";

import { useEffect, useState } from "react";

import {
  AUDIT_EXEMPTION_ABRIDGEMENT_NOTE,
  AUDIT_EXEMPTION_NOTE,
  AUDIT_EXEMPTION_PROVISION,
  AUDIT_EXEMPTION_SOURCE,
  AUDIT_EXEMPTION_SOURCE_LABEL,
  approvalDateLine,
  printedAuditExemption,
  unprintedAuditExemptionSource,
} from "@/lib/audit-exemption";

export type DirectorsConfirmations = {
  not_excluded: boolean | null;
  no_member_notice: boolean | null;
  returns_not_late: boolean | null;
};

const CONFIRMATION_FIELDS = [
  {
    key: "not_excluded" as const,
    testId: "audit-exemption-not-excluded",
    label: "The company is not an excluded class (Fifth Schedule).",
  },
  {
    key: "no_member_notice" as const,
    testId: "audit-exemption-no-member-notice",
    label: "No notice under section 334 has been served.",
  },
  {
    key: "returns_not_late" as const,
    testId: "audit-exemption-returns-not-late",
    label: "Annual returns were not filed late more than once in five years.",
  },
];

function recordedWord(value: boolean | null): string {
  if (value === true) {
    return "Yes";
  }
  if (value === false) {
    return "No";
  }
  return "Not recorded";
}

export function AuditExemptionClaim({
  claimed,
  companyName,
  approvalDate,
  signingDirectors,
  notExcluded,
  noMemberNotice,
  returnsNotLate,
  canRecord,
  lockLabel,
  busy,
  positionMessage,
  noticeMessage,
  error,
  conditionsError,
  onRecord,
  onRecordConditions,
}: {
  claimed: boolean | null;
  companyName: string;
  approvalDate: string | null;
  signingDirectors: readonly string[];
  notExcluded: boolean | null;
  noMemberNotice: boolean | null;
  returnsNotLate: boolean | null;
  canRecord: boolean;
  lockLabel: string | null;
  busy: boolean;
  positionMessage: string | null;
  noticeMessage: string | null;
  error: string | null;
  conditionsError: string | null;
  onRecord: (claimed: boolean | null) => void;
  onRecordConditions: (body: DirectorsConfirmations) => void;
}) {
  const position =
    claimed === true
      ? "Audit exemption claimed"
      : claimed === false
        ? "Not claimed"
        : "Not recorded";
  const [draft, setDraft] = useState<DirectorsConfirmations>({
    not_excluded: notExcluded,
    no_member_notice: noMemberNotice,
    returns_not_late: returnsNotLate,
  });

  useEffect(() => {
    setDraft({
      not_excluded: notExcluded,
      no_member_notice: noMemberNotice,
      returns_not_late: returnsNotLate,
    });
  }, [notExcluded, noMemberNotice, returnsNotLate]);

  const editable = canRecord && lockLabel == null;
  const printed = printedAuditExemption(companyName);
  const sourceText = unprintedAuditExemptionSource();
  const signatories = signingDirectors.map((name) => name.trim()).filter((name) => name !== "");
  const ready =
    draft.not_excluded !== null &&
    draft.no_member_notice !== null &&
    draft.returns_not_late !== null;
  const stored =
    notExcluded === null && noMemberNotice === null && returnsNotLate === null
      ? "Directors' confirmations not recorded"
      : CONFIRMATION_FIELDS.map(
          (field) =>
            `${field.label} ${recordedWord(
              field.key === "not_excluded"
                ? notExcluded
                : field.key === "no_member_notice"
                  ? noMemberNotice
                  : returnsNotLate,
            )}`,
        ).join(" ");

  return (
    <section
      id="audit-exemption-claim"
      className="mt-4 space-y-3 rounded-md border border-line bg-surface-elevated p-4"
      data-testid="audit-exemption-claim"
    >
      <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
        Audit exemption
      </h3>
      <p className="text-sm text-ink" data-testid="audit-exemption-position">
        {position}
      </p>
      {positionMessage ? (
        <p className="text-sm text-ink" data-testid="audit-exemption-message">
          {positionMessage}
        </p>
      ) : null}
      <p className="text-sm font-semibold text-ink" data-testid="audit-exemption-source">
        {AUDIT_EXEMPTION_SOURCE_LABEL}
      </p>
      <p className="text-sm text-ink-secondary" data-testid="audit-exemption-provision">
        {AUDIT_EXEMPTION_SOURCE}. {AUDIT_EXEMPTION_PROVISION}
      </p>
      <h4 className="text-sm font-semibold text-ink" data-testid="audit-exemption-print-heading">
        What prints if the exemption is claimed
      </h4>
      <div data-testid="audit-exemption-printed">
        {printed.map((paragraph) => (
          <p key={paragraph} className="text-sm text-ink">
            {paragraph}
          </p>
        ))}
      </div>
      {claimed === true ? (
        <section className="signature space-y-1" data-testid="audit-exemption-signatures">
          <p className="text-sm text-ink">Approved by the board and signed on its behalf by</p>
          <p className="text-sm text-ink">{approvalDateLine(approvalDate)}</p>
          {signatories.length > 0 ? (
            signatories.map((name) => (
              <p key={name} className="text-sm text-ink">
                {name}
                <br />
                Director
              </p>
            ))
          ) : (
            <p className="text-sm text-ink">A signatory has not been recorded.</p>
          )}
        </section>
      ) : null}
      <p className="text-sm text-ink-secondary" data-testid="audit-exemption-note">
        {AUDIT_EXEMPTION_NOTE}
      </p>
      <details className="text-sm text-ink-secondary" data-testid="audit-exemption-source-text">
        <summary>Source text (CRO), not printed</summary>
        <div className="mt-2 space-y-2">
          {sourceText.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
          <p data-testid="audit-exemption-abridgement">{AUDIT_EXEMPTION_ABRIDGEMENT_NOTE}</p>
        </div>
      </details>
      {noticeMessage ? (
        <p className="text-sm text-ink" data-testid="audit-exemption-notice">
          {noticeMessage}
        </p>
      ) : null}
      {lockLabel ? (
        <p className="text-sm font-semibold text-ink" data-testid="audit-exemption-locked">
          {lockLabel}
        </p>
      ) : null}
      {editable ? (
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
      <div
        id="audit-exemption-conditions"
        className="space-y-3 border-t border-line pt-3"
        data-testid="audit-exemption-conditions"
      >
        <h4 className="text-sm font-semibold text-ink">Directors&apos; confirmations</h4>
        <p className="text-sm text-ink" data-testid="audit-exemption-conditions-position">
          {stored}
        </p>
        {CONFIRMATION_FIELDS.map((field) => (
          <fieldset key={field.key} className="space-y-1" data-testid={field.testId}>
            <legend className="text-sm text-ink">{field.label}</legend>
            {editable ? (
              <div className="flex gap-2">
                <button
                  type="button"
                  data-testid={`${field.testId}-yes`}
                  aria-pressed={draft[field.key] === true}
                  disabled={busy}
                  className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
                  onClick={() =>
                    setDraft((current) => ({ ...current, [field.key]: true }))
                  }
                >
                  Yes
                </button>
                <button
                  type="button"
                  data-testid={`${field.testId}-no`}
                  aria-pressed={draft[field.key] === false}
                  disabled={busy}
                  className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
                  onClick={() =>
                    setDraft((current) => ({ ...current, [field.key]: false }))
                  }
                >
                  No
                </button>
              </div>
            ) : null}
          </fieldset>
        ))}
        {editable ? (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              data-testid="audit-exemption-conditions-record"
              disabled={busy || !ready}
              className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
              onClick={() => onRecordConditions(draft)}
            >
              Record confirmations
            </button>
            <button
              type="button"
              data-testid="audit-exemption-conditions-clear"
              disabled={busy}
              className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
              onClick={() =>
                onRecordConditions({
                  not_excluded: null,
                  no_member_notice: null,
                  returns_not_late: null,
                })
              }
            >
              Clear confirmations
            </button>
          </div>
        ) : null}
        {conditionsError ? (
          <p className="text-sm text-critical" data-testid="audit-exemption-conditions-error">
            {conditionsError}
          </p>
        ) : null}
      </div>
    </section>
  );
}
