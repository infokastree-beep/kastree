"use client";

/**
 * Copilot Ask slide-over for the statements dashboard.
 *
 * Opens from the Ask button beside Export. Posts to
 * POST /trial-balances/{tbId}/copilot (real ask_copilot orchestrator).
 * Citation chips switch dashboard tabs and scroll/highlight the cited line.
 */

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { formatCanonicalLineLabel, formatDate } from "@/lib/utils";
import type { CopilotAskResponse, CopilotCitation } from "@/types";

export type CopilotNavigateTarget = {
  tab?: "Variance" | "Risk";
  anchorId: string;
  /** Auto-expand the matching context strip on the statements page. */
  contextStrip?: "health" | "performance";
};

type CopilotPanelProps = {
  tbId: string;
  open: boolean;
  onClose: () => void;
  onNavigateCitation: (target: CopilotNavigateTarget) => void;
  /** Test-only token source (live E2E harness). */
  getTokenOverride?: () => Promise<string | null>;
};

const SOURCE_LABELS: Record<CopilotCitation["source"], string> = {
  performance: "Performance",
  variance: "Variance",
  expense_mix: "Expense mix",
  risk: "Risk",
  commentary: "Commentary",
  health: "Business health",
  glossary: "Glossary",
};

function citationAnchorId(citation: CopilotCitation): string | null {
  switch (citation.source) {
    case "performance":
      return citation.line_code
        ? `copilot-anchor-performance-${citation.line_code}`
        : "copilot-anchor-performance";
    case "expense_mix":
      return citation.line_code
        ? `copilot-anchor-expense-${citation.line_code}`
        : "copilot-anchor-expense-mix";
    case "variance":
    case "commentary":
      return citation.line_code
        ? `copilot-anchor-variance-${citation.line_code}`
        : "copilot-anchor-variance";
    case "risk":
      return citation.line_code
        ? `copilot-anchor-risk-${citation.line_code}`
        : "copilot-anchor-risk";
    case "health":
      return "copilot-anchor-health";
    case "glossary":
      return null;
    default:
      return null;
  }
}

function citationTab(
  citation: CopilotCitation,
): CopilotNavigateTarget["tab"] | undefined {
  if (citation.source === "variance" || citation.source === "commentary") {
    return "Variance";
  }
  if (citation.source === "risk") {
    return "Risk";
  }
  return undefined;
}

function citationContextStrip(
  citation: CopilotCitation,
): CopilotNavigateTarget["contextStrip"] | undefined {
  if (citation.source === "health") return "health";
  if (citation.source === "performance" || citation.source === "expense_mix") {
    return "performance";
  }
  return undefined;
}

function citationChipLabel(citation: CopilotCitation): string {
  const source = SOURCE_LABELS[citation.source];
  if (citation.line_code) {
    return `${source} · ${formatCanonicalLineLabel(citation.line_code)}`;
  }
  return source;
}

function escapeText(value: string): string {
  return value.replace(/[<>]/g, (ch) => (ch === "<" ? "‹" : "›"));
}

function renderInlineMarkdown(text: string): ReactNode {
  const parts: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(escapeText(text.slice(last, match.index)));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      parts.push(
        <strong key={`m-${key++}`} className="font-semibold text-ink">
          {escapeText(token.slice(2, -2))}
        </strong>,
      );
    } else {
      parts.push(
        <em key={`m-${key++}`} className="italic">
          {escapeText(token.slice(1, -1))}
        </em>,
      );
    }
    last = match.index + token.length;
  }
  if (last < text.length) {
    parts.push(escapeText(text.slice(last)));
  }
  return parts;
}

/** Minimal safe markdown: paragraphs, bold, italics, unordered lists. No HTML. */
function renderAnswerMarkdown(markdown: string): ReactNode {
  const blocks = markdown.trim().split(/\n{2,}/);
  return blocks.map((block, blockIndex) => {
    const lines = block.split("\n");
    const isList = lines.every((line) => /^\s*[-*]\s+/.test(line));
    if (isList) {
      return (
        <ul
          key={`b-${blockIndex}`}
          className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-ink-secondary"
        >
          {lines.map((line, lineIndex) => (
            <li key={`l-${blockIndex}-${lineIndex}`}>
              {renderInlineMarkdown(line.replace(/^\s*[-*]\s+/, ""))}
            </li>
          ))}
        </ul>
      );
    }
    return (
      <p
        key={`b-${blockIndex}`}
        className="text-sm leading-relaxed text-ink-secondary"
      >
        {lines.map((line, lineIndex) => (
          <span key={`s-${blockIndex}-${lineIndex}`}>
            {lineIndex > 0 ? <br /> : null}
            {renderInlineMarkdown(line)}
          </span>
        ))}
      </p>
    );
  });
}

export function CopilotPanel({
  tbId,
  open,
  onClose,
  onNavigateCitation,
  getTokenOverride,
}: CopilotPanelProps) {
  const auth = useAuth();
  const getToken = getTokenOverride ?? auth.getToken;
  const titleId = useId();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [question, setQuestion] = useState("");
  const [isAsking, setIsAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CopilotAskResponse | null>(null);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 50);
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.clearTimeout(focusTimer);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  const ask = useCallback(async () => {
    const trimmed = question.trim();
    if (!trimmed || isAsking) return;
    setIsAsking(true);
    setError(null);
    try {
      const data = await apiFetch<CopilotAskResponse>(
        `/trial-balances/${tbId}/copilot`,
        {
          method: "POST",
          getToken,
          body: JSON.stringify({ question: trimmed }),
        },
      );
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not get an answer. Please try again.",
      );
    } finally {
      setIsAsking(false);
    }
  }, [getToken, isAsking, question, tbId]);

  const handleCitationClick = useCallback(
    (citation: CopilotCitation) => {
      const anchorId = citationAnchorId(citation);
      if (!anchorId) return;
      onNavigateCitation({
        tab: citationTab(citation),
        anchorId,
        contextStrip: citationContextStrip(citation),
      });
    },
    [onNavigateCitation],
  );

  if (!open) return null;

  const refused = Boolean(result?.refused);
  const refusalText =
    result?.refusal_message?.trim() ||
    "I don't have that in the evidence for this period.";

  return (
    <div className="fixed inset-0 z-[60]" data-testid="copilot-panel">
      <button
        type="button"
        aria-label="Close Copilot"
        className="absolute inset-0 bg-ink/30 transition-opacity"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="absolute inset-y-0 right-0 flex h-full w-full max-w-none flex-col border-l border-line bg-surface-elevated shadow-xl sm:max-w-md md:max-w-lg"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2
              id={titleId}
              className="font-display text-lg font-semibold text-ink"
            >
              Ask Copilot
            </h2>
            <p className="mt-1 text-sm text-ink-secondary">
              Answers are grounded in this period&apos;s statements, variance,
              and risk evidence only.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-sm font-semibold text-soft transition-colors hover:bg-accent-muted hover:text-accent"
          >
            Close
          </button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {result?.company_name && result.period_end ? (
            <div
              className="inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink-secondary"
              data-testid="copilot-context-chip"
            >
              <span className="font-semibold text-ink">
                {result.company_name}
              </span>
              <span className="text-soft">·</span>
              <span>{formatDate(result.period_end)}</span>
              {result.prior_period_end ? (
                <>
                  <span className="text-soft">·</span>
                  <span>vs {formatDate(result.prior_period_end)}</span>
                </>
              ) : null}
            </div>
          ) : (
            <div
              className="inline-flex rounded-md border border-line bg-surface px-3 py-1.5 text-xs text-soft"
              data-testid="copilot-context-chip-pending"
            >
              Context appears after the first answer
            </div>
          )}

          <div className="space-y-2">
            <label
              htmlFor="copilot-question"
              className="text-xs font-semibold uppercase tracking-[0.12em] text-soft"
            >
              Question
            </label>
            <textarea
              id="copilot-question"
              ref={inputRef}
              rows={3}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault();
                  void ask();
                }
              }}
              placeholder="e.g. What moved in revenue and operating expenses vs prior?"
              className="w-full resize-none rounded-md border border-line bg-surface px-3 py-2.5 text-sm text-ink shadow-sm placeholder:text-soft focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              data-testid="copilot-question-input"
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-soft">⌘/Ctrl + Enter to send</p>
              <button
                type="button"
                disabled={isAsking || !question.trim()}
                onClick={() => void ask()}
                className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover disabled:opacity-50"
                data-testid="copilot-ask-submit"
              >
                {isAsking ? "Thinking…" : "Ask"}
              </button>
            </div>
          </div>

          {error ? (
            <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
              {error}
            </p>
          ) : null}

          {isAsking && !result ? (
            <p className="text-sm text-soft" data-testid="copilot-loading">
              Gathering evidence and drafting an answer…
            </p>
          ) : null}

          {result && refused ? (
            <div
              className="rounded-md border border-line bg-surface-elevated p-5"
              data-testid="copilot-refusal"
            >
              <h3 className="font-display text-base font-semibold text-ink">
                Answer
              </h3>
              <p className="mt-2 text-sm text-ink-secondary">{refusalText}</p>
            </div>
          ) : null}

          {result && !refused ? (
            <div className="space-y-3" data-testid="copilot-answer">
              <div className="space-y-3 rounded-md border border-line bg-surface p-4">
                {renderAnswerMarkdown(result.answer_markdown)}
              </div>
              {result.citations.length > 0 ? (
                <div className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
                    Sources
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {result.citations.map((citation, index) => {
                      const anchorId = citationAnchorId(citation);
                      const label = citationChipLabel(citation);
                      if (!anchorId) {
                        return (
                          <span
                            key={`c-${index}-${label}`}
                            className="rounded-md border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink-secondary"
                          >
                            {label}
                          </span>
                        );
                      }
                      return (
                        <button
                          key={`c-${index}-${label}`}
                          type="button"
                          onClick={() => handleCitationClick(citation)}
                          className="rounded-md border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-accent transition-colors hover:border-accent hover:bg-accent-muted"
                          data-testid={`copilot-citation-${citation.source}`}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
