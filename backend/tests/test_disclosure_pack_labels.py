"""Pack labels for disclosure questions and trial-balance reasons.

These fields are wording only. includeWhen, note bodies, and engine figures
stay as they are.
"""

from __future__ import annotations

import json
from pathlib import Path

from findraft.engine.notes import ANSWER_FLAGS, DERIVED

_PACK = (
    Path(__file__).resolve().parents[2]
    / "findraft"
    / "content"
    / "frs102-1a-ie"
    / "2024.09"
)


def _load(name: str) -> dict[str, object]:
    loaded = json.loads((_PACK / name).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError(f"{name} is not an object")
    return loaded


def test_checklist_questions_do_not_change_inclusion() -> None:
    checklist = _load("disclosure-checklist.json")
    items = checklist["items"]
    assert isinstance(items, list)
    assert len(items) == 55
    flags: set[str] = set()
    for item in items:
        assert isinstance(item, dict)
        question = item.get("question")
        assert isinstance(question, str) and question.strip()
        assert "£" not in question and "€" not in question and "$" not in question
        flag = item.get("flag")
        assert "flag" in item
        if flag is None:
            continue
        assert isinstance(flag, str)
        assert flag in ANSWER_FLAGS
        assert flag not in DERIVED
        flags.add(flag)
    extras = _load("disclosure-questions.json")
    extra_rows = extras["questions"]
    assert isinstance(extra_rows, list)
    for row in extra_rows:
        assert isinstance(row, dict)
        flag = row["flag"]
        question = row["question"]
        assert isinstance(flag, str) and flag in ANSWER_FLAGS
        assert isinstance(question, str) and question.strip()
        assert flag not in flags
        flags.add(flag)
    assert flags == set(ANSWER_FLAGS)


def test_reason_labels_cover_derived_facts_without_amounts() -> None:
    labels = _load("reason-labels.json")
    assert set(labels) == set(DERIVED)
    for name, label in labels.items():
        assert isinstance(label, str) and label.strip()
        assert any(character.isdigit() for character in label) is False
        assert name not in ANSWER_FLAGS


def test_pension_question_stays_on_the_commitments_note() -> None:
    checklist = _load("disclosure-checklist.json")
    items = checklist["items"]
    assert isinstance(items, list)
    pension = next(item for item in items if item["id"] == "1AD.32")
    assert pension["flag"] == "PENSION_COMMITMENT"
    assert pension["note"] == "N9_COMMITMENTS"
    assert pension["includeWhen"] == "PENSION_COMMITMENT == true"
    assert pension["question"] == "Are there retirement-benefit commitments?"
