"""Ground Copilot answers against the evidence pack.

CRITICAL: if a sentence cites a figure (money or %) that is not in the evidence
pack, that sentence is dropped. This is enforced in code — never left to the
model. Citations whose line_code is absent from the pack are also dropped.
"""

from __future__ import annotations

import re

from app.schemas.copilot import (
    REFUSAL_MESSAGE,
    CopilotAnswer,
    CopilotCitation,
    EvidencePack,
    GroundedCopilotAnswer,
    normalize_numeric_token,
)

# Money-like or percent-like tokens in prose (optional currency / % suffix).
# Prefer thousand-grouped forms first so "20000.00" is not split into "200"+"00.00".
_NUMERIC_TOKEN_RE = re.compile(
    r"[£€$]?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?"
    r"|[£€$]?-?\d+(?:\.\d+)?%?"
)

# ISO dates in prose are not monetary evidence — mask before token extraction
# so "2026-09-20" does not become ungrounded tokens 2026 / 09 / 20.
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# Split on sentence boundaries while keeping abbreviations crude-safe enough for v1.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ])")


def ground_answer(
    answer: CopilotAnswer,
    pack: EvidencePack,
) -> GroundedCopilotAnswer:
    """Drop ungrounded sentences and invalid citations; refuse if nothing remains."""
    if answer.refused or pack.refusal_reason:
        message = answer.refusal_message or pack.refusal_reason or REFUSAL_MESSAGE
        return GroundedCopilotAnswer(
            answer_markdown="",
            citations=[],
            confidence=None,
            refused=True,
            refusal_message=message,
            dropped_sentence_count=0,
        )

    allowed_amounts = pack.all_amount_strings()
    allowed_codes = pack.all_line_codes()

    sentences = _split_sentences(answer.answer_markdown)
    kept: list[str] = []
    dropped = 0
    for sentence in sentences:
        if _sentence_is_grounded(sentence, allowed_amounts=allowed_amounts):
            kept.append(sentence)
        else:
            dropped += 1

    citations = [
        citation
        for citation in answer.citations
        if _citation_is_grounded(citation, allowed_codes=allowed_codes)
    ]

    if not kept:
        return GroundedCopilotAnswer(
            answer_markdown="",
            citations=[],
            confidence=None,
            refused=True,
            refusal_message=REFUSAL_MESSAGE,
            dropped_sentence_count=dropped,
        )

    return GroundedCopilotAnswer(
        answer_markdown=" ".join(kept).strip(),
        citations=citations,
        confidence=answer.confidence,
        refused=False,
        refusal_message=None,
        dropped_sentence_count=dropped,
    )


def _split_sentences(text: str) -> list[str]:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return []
    parts = _SENTENCE_SPLIT_RE.split(cleaned)
    return [part.strip() for part in parts if part.strip()]


def _sentence_is_grounded(sentence: str, *, allowed_amounts: set[str]) -> bool:
    """True when every numeric token in the sentence appears in the evidence pack.

    Sentences with no numeric tokens (pure narrative / glossary) are allowed.
    ISO dates are masked so period labels are not mistaken for money figures.
    """
    scrubbed = _ISO_DATE_RE.sub(" ", sentence)
    tokens = _NUMERIC_TOKEN_RE.findall(scrubbed)
    if not tokens:
        return True
    for token in tokens:
        normalized = normalize_numeric_token(token)
        if not normalized:
            continue
        if normalized not in allowed_amounts:
            return False
    return True


def _citation_is_grounded(
    citation: CopilotCitation,
    *,
    allowed_codes: set[str],
) -> bool:
    if citation.line_code is None:
        return True
    return citation.line_code in allowed_codes
