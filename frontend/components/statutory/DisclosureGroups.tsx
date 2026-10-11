"use client";

import { useState } from "react";
import Link from "next/link";

import {
  answerAfterMark,
  groupDisclosureQuestions,
  noteHref,
  remainingNoSummary,
  type DisclosureQuestion,
} from "@/lib/disclosure-groups";

function groupSlug(group: string): string {
  return group
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function DisclosureGroups({
  yearEndId,
  questions,
  canAnswer,
  busy,
  onAnswer,
  onMarkRemaining,
}: {
  yearEndId: string;
  questions: readonly DisclosureQuestion[];
  canAnswer: boolean;
  busy: boolean;
  onAnswer: (flagName: string, answer: "yes" | "no") => Promise<void>;
  onMarkRemaining: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const groups = groupDisclosureQuestions(questions);
  const summary = remainingNoSummary(questions);
  const locked = busy || !canAnswer;

  async function confirmMark(): Promise<void> {
    try {
      await onMarkRemaining();
      setOpen(false);
    } catch {
      // The workspace already shows the error. The answers stay as they were.
    }
  }

  return (
    <section className="space-y-4" data-testid="statutory-disclosures">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
          Disclosure questions
        </h2>
        {summary.total > 0 ? (
          <button
            type="button"
            data-testid="statutory-mark-remaining-no"
            disabled={locked}
            className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
            onClick={() => setOpen(true)}
          >
            Mark all remaining as No
          </button>
        ) : null}
      </div>
      {open ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="statutory-mark-remaining-title"
          data-testid="statutory-mark-remaining-dialog"
          className="max-w-xl space-y-3 rounded-md border border-line bg-surface-elevated p-4 text-ink"
        >
          <p id="statutory-mark-remaining-title" className="text-sm">
            This will answer No to {summary.total}{" "}
            {summary.total === 1 ? "question" : "questions"}.
          </p>
          <ul className="space-y-1 text-sm" data-testid="statutory-mark-remaining-groups">
            {summary.groups.map((group) => (
              <li key={group.group}>
                {group.group}: {group.count}
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <button
              type="button"
              data-testid="statutory-mark-remaining-confirm"
              disabled={locked}
              className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accent-foreground disabled:opacity-50"
              onClick={() => void confirmMark()}
            >
              Confirm
            </button>
            <button
              type="button"
              className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink"
              onClick={() => setOpen(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
      {groups.map((group) => (
        <section key={group.group} data-testid={`statutory-disclosure-group-${groupSlug(group.group)}`}>
          <h3 className="text-sm font-semibold">
            {group.group}
            <span className="ml-2 font-normal text-ink-secondary">
              {group.answered} answered, {group.unanswered} unanswered
            </span>
          </h3>
          {group.note ? (
            <Link
              href={noteHref(yearEndId, group.note)}
              className="text-sm font-semibold underline"
              data-testid={`statutory-disclosure-note-${groupSlug(group.group)}`}
            >
              View note
            </Link>
          ) : null}
          <ul className="mt-2 space-y-2">
            {group.questions.map((question) => {
              const shown = answerAfterMark(question, null);
              return (
                <li
                  key={question.flag_name}
                  data-testid={`statutory-disclosure-${question.flag_name}`}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line bg-surface-elevated px-4 py-3"
                >
                  <span className="text-sm text-ink">
                    {question.question}
                    {shown !== "unanswered" ? (
                      <span
                        className="ml-2 font-semibold"
                        data-testid={`statutory-disclosure-answer-${question.flag_name}`}
                      >
                        {shown === "yes" ? "Yes" : "No"}
                      </span>
                    ) : null}
                  </span>
                  <span className="flex gap-2">
                    <button
                      type="button"
                      disabled={locked}
                      onClick={() => void onAnswer(question.flag_name, "yes")}
                      className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
                    >
                      Yes
                    </button>
                    <button
                      type="button"
                      disabled={locked}
                      onClick={() => void onAnswer(question.flag_name, "no")}
                      className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
                    >
                      No
                    </button>
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </section>
  );
}
