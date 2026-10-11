"""Pack disclosure questions for the draft panel.

Derived trial-balance facts are not questions. The question sentence is the
pack's own `question` field. Group labels follow the statutory checklist table.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from findraft.engine.notes import ANSWER_FLAGS, DERIVED
from findraft.engine.pack import pack_dir

AnswerState = Literal["yes", "no", "unanswered"]

# Flag, group label, note code. Order is the disclosures checklist table.
_CATALOGUE: tuple[tuple[str, str, str | None], ...] = (
    ("FORMAT_CHANGE", "Accounting policies", "N1_POLICIES"),
    ("POLICY_CHANGE", "Accounting policies", "N1_POLICIES"),
    ("PRIOR_RECLASS", "Accounting policies", "N1_POLICIES"),
    ("GOING_CONCERN_DEPARTURE", "Accounting policies", "N1_POLICIES"),
    ("GOODWILL", "Fixed assets", "N2_FA"),
    ("DEV_COSTS", "Fixed assets", "N2_FA"),
    ("DEV_COSTS_UNREALISED", "Fixed assets", "N2_FA"),
    ("REVALUATION_RESERVE", "Fixed assets", "N2_FA"),
    ("REVAL_TRANSFER", "Fixed assets", "N6_CAPITAL"),
    ("CAPITALISED_BORROWING", "Fixed assets", "N2_FA"),
    ("IMPAIRMENT", "Fixed assets", "N2_FA"),
    ("IMPAIRMENT_REVERSAL", "Fixed assets", "N2_FA"),
    ("FI_FVPL", "Fair value", "N3_DEBTORS"),
    ("NONFI_FV", "Fair value", "N3_DEBTORS"),
    ("FV_VS_HC_DIFFERS", "Fair value", "N3_DEBTORS"),
    ("FV_DESIGNATION", "Fair value", None),
    ("SECURED_CREDITORS", "Creditors", "N4_CREDITORS"),
    ("CHARGES_EXIST", "Commitments", "N9_COMMITMENTS"),
    ("GUARANTEES_EXIST", "Commitments", "N9_COMMITMENTS"),
    ("UNCOMMITTED", "Commitments", "N9_COMMITMENTS"),
    ("PENSION_COMMITMENT", "Commitments", "N9_COMMITMENTS"),
    ("OFF_BALANCE_ARRANGEMENT", "Commitments", "N9_COMMITMENTS"),
    ("COMMITMENTS_EXIST", "Commitments", "N9_COMMITMENTS"),
    ("SUBSEQUENT_EVENTS", "Commitments", "N9_COMMITMENTS"),
    ("PAST_DIRECTOR_PENSION_COMMITMENTS", "Directors", "N7_RPT"),
    ("PAST_DIRECTOR_BENEFITS", "Directors", "N7_RPT"),
    ("THIRD_PARTY_DIRECTOR_SERVICES", "Directors", "N5_LOANS"),
    ("CONNECTED_LOANS", "Directors", "N5_LOANS"),
    ("DIRECTOR_LOAN_AGREEMENTS", "Directors", "N5_LOANS"),
    ("DIRECTOR_GUARANTEES", "Directors", "N5_LOANS"),
    ("DIRECTOR_GUARANTEE_AGREEMENTS", "Directors", "N5_LOANS"),
    ("DIRECTOR_MATERIAL_INTEREST", "Directors", "N7_RPT"),
    ("SMALL_GROUP_EXEMPTION", "Capital and group", "N6_CAPITAL"),
    ("OWN_SHARES_HELD", "Capital and group", "N6_CAPITAL"),
    ("IS_SUBSIDIARY", "Capital and group", "N6_CAPITAL"),
    ("RPT_EXISTS", "Related parties", "N7_RPT"),
    ("HAS_EMPLOYEES", "Employees", "N8_EMPLOYEES"),
    ("DIRECTORS_EXIST", "Other", "N0_ENTITY"),
    ("REQUIRED_BY_FORMAT", "Other", None),
    ("FORMAT_COMBINED", "Other", None),
    ("SET_OFF_USED", "Other", None),
    ("MULTI_ITEM_ASSET", "Other", None),
    ("HAS_FOREIGN", "Other", None),
)


@dataclass(frozen=True)
class DisclosureQuestion:
    flag_name: str
    question: str
    group: str
    note: str | None
    answer: AnswerState


def catalogue_flags() -> frozenset[str]:
    return frozenset(flag for flag, _group, _note in _CATALOGUE)


@lru_cache(maxsize=1)
def _question_text() -> dict[str, str]:
    """First pack question for a flag. A later checklist row that shares the flag is a particular, not a second question."""
    directory = pack_dir()
    found: dict[str, str] = {}
    checklist = json.loads(
        (directory / "disclosure-checklist.json").read_text(encoding="utf-8")
    )
    items = checklist.get("items") if isinstance(checklist, dict) else None
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            flag = item.get("flag")
            question = item.get("question")
            if (
                isinstance(flag, str)
                and flag not in found
                and isinstance(question, str)
                and question.strip()
            ):
                found[flag] = question
    extras = json.loads(
        (directory / "disclosure-questions.json").read_text(encoding="utf-8")
    )
    questions = extras.get("questions") if isinstance(extras, dict) else None
    if isinstance(questions, list):
        for item in questions:
            if not isinstance(item, dict):
                continue
            flag = item.get("flag")
            question = item.get("question")
            if (
                isinstance(flag, str)
                and flag not in found
                and isinstance(question, str)
                and question.strip()
            ):
                found[flag] = question
    return found


def present_disclosure_questions(
    flags: Mapping[str, bool],
) -> tuple[DisclosureQuestion, ...]:
    """One row per preparer flag. Missing flags stay unanswered. Derived facts are omitted."""
    texts = _question_text()
    rows: list[DisclosureQuestion] = []
    for flag_name, group, note in _CATALOGUE:
        if flag_name in DERIVED or flag_name not in ANSWER_FLAGS:
            raise ValueError(f"{flag_name} is not a disclosure question")
        question = texts.get(flag_name)
        if question is None:
            raise ValueError(f"disclosure question missing for {flag_name}")
        stored = flags.get(flag_name)
        if stored is True:
            answer: AnswerState = "yes"
        elif stored is False:
            answer = "no"
        else:
            answer = "unanswered"
        rows.append(
            DisclosureQuestion(
                flag_name=flag_name,
                question=question,
                group=group,
                note=note,
                answer=answer,
            )
        )
    return tuple(rows)
