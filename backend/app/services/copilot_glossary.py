"""Static glossary entries for Copilot definition questions (v1)."""

from __future__ import annotations

from app.schemas.copilot import EvidenceGlossaryEntry

GLOSSARY_ENTRIES: tuple[EvidenceGlossaryEntry, ...] = (
    EvidenceGlossaryEntry(
        term="gross profit",
        definition=(
            "Revenue less cost of sales. Shows the margin earned on goods or "
            "services before operating expenses."
        ),
    ),
    EvidenceGlossaryEntry(
        term="gross margin",
        definition=(
            "Gross profit as a share of revenue. A higher margin means more of "
            "each unit of revenue is retained after direct costs."
        ),
    ),
    EvidenceGlossaryEntry(
        term="operating expenses",
        definition=(
            "Day-to-day running costs of the business (for example admin, "
            "selling, and general expenses), excluding cost of sales."
        ),
    ),
    EvidenceGlossaryEntry(
        term="net profit",
        definition=(
            "Profit after operating expenses, interest, and tax (as mapped on "
            "the statement of profit or loss)."
        ),
    ),
    EvidenceGlossaryEntry(
        term="material variance",
        definition=(
            "A period-on-period movement that exceeds the company's materiality "
            "thresholds (percentage and/or absolute amount)."
        ),
    ),
    EvidenceGlossaryEntry(
        term="statement of financial position",
        definition=(
            "The balance sheet: assets, liabilities, and equity at the period end."
        ),
    ),
    EvidenceGlossaryEntry(
        term="statement of profit or loss",
        definition=(
            "The income statement for the period: revenue, costs, and profit."
        ),
    ),
    EvidenceGlossaryEntry(
        term="variance",
        definition=(
            "The difference between the current period and a prior period for "
            "the same statement line."
        ),
    ),
    EvidenceGlossaryEntry(
        term="business health",
        definition=(
            "An AI-drafted executive summary of directional trends (margin, "
            "operating leverage, cash). It does not invent figures."
        ),
    ),
)


def lookup_glossary(question: str) -> list[EvidenceGlossaryEntry]:
    """Return glossary entries whose terms appear in the question."""
    lowered = question.lower()
    return [entry for entry in GLOSSARY_ENTRIES if entry.term in lowered]
