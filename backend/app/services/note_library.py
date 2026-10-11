"""Preparer omissions and additions for pack narrative blocks.

NULL on the draft means the preparer has not omitted or added a block.
The engine still chooses the default set. This module only drops a
disclosure block the engine included, or prints one the engine left out.
"""

from __future__ import annotations

import importlib.util
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from findraft.engine.notes import ANSWER_FLAGS, DERIVED
from findraft.engine.pack import pack_dir
from findraft.engine.predicates import Unanswered, evaluate

from app.services.reconciliation import ReconciliationCheck

ReasonName = Literal[
    "always",
    "trial_balance",
    "disclosure_yes",
    "unanswered",
    "disclosure_no",
    "omitted",
    "added",
]
LibraryAction = Literal["omit", "restore", "add", "remove"]
_KEYWORDS = frozenset({"AND", "OR", "NOT", "TRUE", "FALSE"})
_NAME = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_COMMITMENT_PARENT = "N9_COMMITMENTS"
_RELATED_PARTY = "N7_RPT"

_COMMITMENT_SPECS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "capital_commitments",
        "Capital commitments",
        "UNCOMMITTED != 0",
        ("UNCOMMITTED",),
    ),
    (
        "pension_commitments",
        "Retirement benefit commitments",
        "PENSION_COMMITMENT == true",
        ("PENSION_COMMITMENT",),
    ),
    (
        "guarantee_particulars",
        "Guarantees and security",
        "GUARANTEES_EXIST == true",
        ("GUARANTEES_EXIST",),
    ),
    (
        "charge_particulars",
        "Charges on assets",
        "CHARGES_EXIST == true",
        ("CHARGES_EXIST",),
    ),
    (
        "subsequent_events",
        "Subsequent events",
        "SUBSEQUENT_EVENTS == true",
        ("SUBSEQUENT_EVENTS",),
    ),
)


class LibraryRejected(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class NoteLibrary:
    omitted: tuple[str, ...]
    added: tuple[str, ...]


@dataclass(frozen=True)
class BlockSpec:
    block_id: str
    title: str
    kind: Literal["always", "trial_balance", "disclosure"]
    predicate: str
    question_flags: tuple[str, ...]
    placeholder_key: str | None
    pack_heading: str | None
    controllable: bool
    parent: str | None


@dataclass(frozen=True)
class LibraryRow:
    block_id: str
    title: str
    reason: ReasonName
    sentence: str
    can_omit: bool
    can_restore: bool
    can_add: bool
    can_remove: bool


@dataclass(frozen=True)
class PrintedBlock:
    block_id: str
    title: str
    heading: str
    placeholder_key: str
    added: bool


@dataclass(frozen=True)
class CommitmentPrint:
    mode: Literal["pending", "blocks", "absent"]
    blocks: tuple[PrintedBlock, ...]


def parse_note_library(raw: object) -> NoteLibrary:
    """Read the stored object. NULL is an empty library."""
    if raw is None:
        return NoteLibrary((), ())
    if not isinstance(raw, dict):
        raise LibraryRejected("note library is unreadable")
    if set(raw) - {"omitted", "added"}:
        raise LibraryRejected("note library is unreadable")
    omitted = _id_list(raw.get("omitted", []))
    added = _id_list(raw.get("added", []))
    if set(omitted) & set(added):
        raise LibraryRejected("note library is unreadable")
    return NoteLibrary(tuple(omitted), tuple(added))


def to_storage(library: NoteLibrary) -> dict[str, object] | None:
    """NULL when the preparer has neither omitted nor added a block."""
    if not library.omitted and not library.added:
        return None
    return {"omitted": list(library.omitted), "added": list(library.added)}


def present_rows(
    ctx: dict[str, object],
    library: NoteLibrary,
) -> tuple[LibraryRow, ...]:
    pending_parent = _parent_pending(ctx)
    return tuple(
        _row(spec, ctx, library, parent_pending=pending_parent)
        for spec in _catalogue()
    )


def apply_library_action(
    library: NoteLibrary,
    *,
    block_id: str,
    action: LibraryAction,
    ctx: dict[str, object],
) -> NoteLibrary:
    """Return the next library. Raises LibraryRejected and writes nothing."""
    spec = _spec(block_id)
    if spec is None:
        raise LibraryRejected("unknown note block")
    if not spec.controllable:
        if spec.kind == "always":
            raise LibraryRejected("this note is always included")
        if spec.kind == "trial_balance":
            raise LibraryRejected("this note follows the trial balance")
        raise LibraryRejected("this note is changed one block at a time")
    row = _row(spec, ctx, library, parent_pending=_parent_pending(ctx))
    omitted = set(library.omitted)
    added = set(library.added)
    if action == "omit":
        if not row.can_omit:
            _refuse_control(row, "omit")
        omitted.add(block_id)
        added.discard(block_id)
    elif action == "restore":
        if not row.can_restore:
            _refuse_control(row, "restore")
        omitted.discard(block_id)
    elif action == "add":
        if not row.can_add:
            _refuse_control(row, "add")
        added.add(block_id)
        omitted.discard(block_id)
    else:
        if not row.can_remove:
            _refuse_control(row, "remove")
        added.discard(block_id)
    return NoteLibrary(tuple(sorted(omitted)), tuple(sorted(added)))


def library_notices(
    ctx: dict[str, object],
    library: NoteLibrary,
) -> tuple[ReconciliationCheck, ...]:
    """NOTICE checks. None of these block FINAL."""
    pending_parent = _parent_pending(ctx)
    omitted_titles: list[str] = []
    added_titles: list[str] = []
    blank_titles: list[str] = []
    for spec in _catalogue():
        if not spec.controllable:
            continue
        reason = _reason(spec, ctx, library, parent_pending=pending_parent)
        if reason == "omitted":
            omitted_titles.append(spec.title)
        elif reason == "added":
            added_titles.append(spec.title)
            if spec.placeholder_key is not None:
                blank_titles.append(spec.title)
    notices: list[ReconciliationCheck] = []
    if omitted_titles:
        notices.append(
            ReconciliationCheck(
                code="V-NOTE-001",
                severity="NOTICE",
                passed=False,
                message="Omitted as immaterial: " + ", ".join(sorted(omitted_titles)) + ".",
            )
        )
    if added_titles:
        notices.append(
            ReconciliationCheck(
                code="V-NOTE-002",
                severity="NOTICE",
                passed=False,
                message=(
                    "Added by the preparer: " + ", ".join(sorted(added_titles)) + "."
                ),
            )
        )
    if blank_titles:
        notices.append(
            ReconciliationCheck(
                code="V-NOTE-003",
                severity="NOTICE",
                passed=False,
                message=(
                    ", ".join(sorted(blank_titles))
                    + ": particulars are not recorded."
                ),
            )
        )
    return tuple(notices)


def include_policy(
    policy_id: str,
    predicate: str,
    ctx: dict[str, object],
    library: NoteLibrary,
) -> bool:
    """Whether this policy paragraph prints. Unanswered policies stay out."""
    kind = _predicate_kind(predicate)
    if kind == "always":
        return True
    state = _predicate_state(predicate, ctx)
    if state == "unanswered":
        return False
    if kind == "trial_balance":
        return state == "yes"
    if state == "yes":
        return policy_id not in library.omitted
    return policy_id in library.added


def related_party_override(
    ctx: dict[str, object],
    library: NoteLibrary,
) -> Literal["keep", "drop", "force"]:
    spec = _spec(_RELATED_PARTY)
    if spec is None:
        return "keep"
    reason = _reason(spec, ctx, library, parent_pending=False)
    if reason == "omitted":
        return "drop"
    if reason == "added":
        return "force"
    return "keep"


def commitment_print(
    template: dict[str, object],
    ctx: dict[str, object],
    library: NoteLibrary,
) -> CommitmentPrint:
    """Pending line, the blocks that print, or no commitments note."""
    condition = template.get("includeWhen")
    if not isinstance(condition, str):
        raise LibraryRejected("commitments note has no includeWhen")
    if _any_unanswered(condition, ctx):
        return CommitmentPrint("pending", ())
    headings = template.get("blocks")
    pack_headings = headings if isinstance(headings, dict) else {}
    printed: list[PrintedBlock] = []
    for spec in _catalogue():
        if spec.parent != _COMMITMENT_PARENT or spec.placeholder_key is None:
            continue
        reason = _reason(spec, ctx, library, parent_pending=False)
        if reason not in {"disclosure_yes", "omitted", "added"}:
            continue
        if reason == "omitted":
            continue
        heading = pack_headings.get(spec.block_id)
        text = heading.strip() if isinstance(heading, str) and heading.strip() else spec.title
        printed.append(
            PrintedBlock(
                block_id=spec.block_id,
                title=spec.title,
                heading=text,
                placeholder_key=spec.placeholder_key,
                added=reason == "added",
            )
        )
    if not printed:
        return CommitmentPrint("absent", ())
    return CommitmentPrint("blocks", tuple(printed))


def effective_ids(
    ctx: dict[str, object],
    library: NoteLibrary,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Ids that changed the print, for the statement payload."""
    pending_parent = _parent_pending(ctx)
    omitted: list[str] = []
    added: list[str] = []
    for spec in _catalogue():
        if not spec.controllable:
            continue
        reason = _reason(spec, ctx, library, parent_pending=pending_parent)
        if reason == "omitted":
            omitted.append(spec.block_id)
        elif reason == "added":
            added.append(spec.block_id)
    return tuple(omitted), tuple(added)


def _refuse_control(row: LibraryRow, action: str) -> None:
    if row.reason == "unanswered":
        raise LibraryRejected("this note is waiting for a disclosure answer")
    if action == "omit":
        raise LibraryRejected("this block is not included")
    if action == "add":
        raise LibraryRejected("this block is already included")
    if action == "restore":
        raise LibraryRejected("this block is not omitted")
    raise LibraryRejected("this block was not added")


def _row(
    spec: BlockSpec,
    ctx: dict[str, object],
    library: NoteLibrary,
    *,
    parent_pending: bool,
) -> LibraryRow:
    reason = _reason(spec, ctx, library, parent_pending=parent_pending)
    sentence = _sentence(spec, reason, ctx)
    controllable = spec.controllable and not parent_pending
    return LibraryRow(
        block_id=spec.block_id,
        title=spec.title,
        reason=reason,
        sentence=sentence,
        can_omit=controllable and reason == "disclosure_yes",
        can_restore=controllable and reason == "omitted",
        can_add=controllable and reason == "disclosure_no",
        can_remove=controllable and reason == "added",
    )


def _reason(
    spec: BlockSpec,
    ctx: dict[str, object],
    library: NoteLibrary,
    *,
    parent_pending: bool,
) -> ReasonName:
    if spec.kind == "always":
        return "always"
    if spec.parent == _COMMITMENT_PARENT and parent_pending:
        return "unanswered"
    state = _predicate_state(spec.predicate, ctx)
    if spec.kind == "trial_balance":
        return "trial_balance"
    if state == "unanswered":
        return "unanswered"
    if state == "yes":
        if spec.controllable and spec.block_id in library.omitted:
            return "omitted"
        return "disclosure_yes"
    if spec.controllable and spec.block_id in library.added:
        return "added"
    return "disclosure_no"


def _sentence(spec: BlockSpec, reason: ReasonName, ctx: dict[str, object]) -> str:
    if reason == "always":
        return "This note is always included."
    if reason == "trial_balance":
        label = _balance_label(spec, ctx)
        state = _predicate_state(spec.predicate, ctx)
        if state == "yes":
            return f"Included because {label} has a balance."
        return f"Left out because {label} has no balance."
    question = _question(spec, ctx)
    if reason == "disclosure_yes":
        return f"Included because the answer to “{question}” is Yes."
    if reason == "unanswered":
        return f"Waiting for an answer to “{question}”."
    if reason == "disclosure_no":
        return f"Left out because the answer to “{question}” is No."
    if reason == "omitted":
        return f"Omitted as immaterial. The answer to “{question}” is still Yes."
    return f"Added by the preparer. The answer to “{question}” is No."


def _question(spec: BlockSpec, ctx: dict[str, object]) -> str:
    questions = _questions()
    for flag in spec.question_flags:
        if ctx.get(flag) is None:
            return questions.get(flag, flag)
    for flag in spec.question_flags:
        value = ctx.get(flag)
        if value is True:
            return questions.get(flag, flag)
    if spec.question_flags:
        return questions.get(spec.question_flags[0], spec.question_flags[0])
    return spec.title


def _balance_label(spec: BlockSpec, ctx: dict[str, object]) -> str:
    labels = _reason_labels()
    names = [name for name in _predicate_names(spec.predicate) if name in DERIVED]
    for name in names:
        state = _predicate_state(f"{name} != 0", ctx)
        if state == "yes":
            return labels.get(name, name)
    if names:
        return labels.get(names[0], names[0])
    return spec.title


def _parent_pending(ctx: dict[str, object]) -> bool:
    spec = _spec(_COMMITMENT_PARENT)
    if spec is None:
        return False
    return _any_unanswered(spec.predicate, ctx)


def _predicate_state(
    predicate: str,
    ctx: dict[str, object],
) -> Literal["yes", "no", "unanswered"]:
    if predicate == "always":
        return "yes"
    if _any_unanswered(predicate, ctx):
        return "unanswered"
    try:
        affirmed = evaluate(predicate, ctx)
    except Unanswered:
        return "unanswered"
    return "yes" if affirmed else "no"


def _any_unanswered(predicate: str, ctx: dict[str, object]) -> bool:
    if predicate == "always":
        return False
    return any(ctx.get(name) is None for name in _predicate_names(predicate))


def _predicate_names(predicate: str) -> tuple[str, ...]:
    return tuple(
        name for name in _NAME.findall(predicate) if name not in _KEYWORDS
    )


def _predicate_kind(predicate: str) -> Literal["always", "trial_balance", "disclosure"]:
    if predicate == "always":
        return "always"
    names = _predicate_names(predicate)
    if names and all(name in DERIVED for name in names):
        return "trial_balance"
    return "disclosure"


def _spec(block_id: str) -> BlockSpec | None:
    for spec in _catalogue():
        if spec.block_id == block_id:
            return spec
    return None


def _id_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        raise LibraryRejected("note library is unreadable")
    seen: set[str] = set()
    ids: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip() or item in seen:
            raise LibraryRejected("note library is unreadable")
        seen.add(item)
        ids.append(item)
    return ids


@lru_cache(maxsize=1)
def _catalogue() -> tuple[BlockSpec, ...]:
    directory = pack_dir()
    notes = _note_templates(directory)
    questions = _questions()
    labels = _reason_labels()
    del questions, labels
    rows: list[BlockSpec] = []
    for code in (
        "N0_ENTITY",
        "N1_POLICIES",
        "N2_FA",
        "N3_DEBTORS",
        "N4_CREDITORS",
        "N5_LOANS",
        "N6_CAPITAL",
        "N7_RPT",
        "N8_EMPLOYEES",
        "N9_COMMITMENTS",
    ):
        template = notes[code]
        condition = template.get("includeWhen")
        if not isinstance(condition, str) or not condition:
            raise LibraryRejected(f"note {code} has no includeWhen")
        kind = _predicate_kind(condition)
        title = _plain_title(template.get("title"), code)
        flags = tuple(
            name for name in _predicate_names(condition) if name in ANSWER_FLAGS
        )
        rows.append(
            BlockSpec(
                block_id=code,
                title=title,
                kind=kind,
                predicate=condition,
                question_flags=flags,
                placeholder_key=None,
                pack_heading=None,
                controllable=code == _RELATED_PARTY,
                parent=None,
            )
        )
        if code == "N1_POLICIES":
            rows.extend(_policy_specs())
        if code == _COMMITMENT_PARENT:
            headings = template.get("blocks")
            pack_headings = headings if isinstance(headings, dict) else {}
            for block_id, title, predicate, flag_names in _COMMITMENT_SPECS:
                heading = pack_headings.get(block_id)
                rows.append(
                    BlockSpec(
                        block_id=block_id,
                        title=title,
                        kind="disclosure",
                        predicate=predicate,
                        question_flags=flag_names,
                        placeholder_key=block_id,
                        pack_heading=heading if isinstance(heading, str) else None,
                        controllable=True,
                        parent=_COMMITMENT_PARENT,
                    )
                )
    return tuple(rows)


def _policy_specs() -> tuple[BlockSpec, ...]:
    specs: list[BlockSpec] = []
    for policy in _load_policies():
        policy_id = policy.get("id")
        predicate = policy.get("appliesWhen")
        title = policy.get("title")
        if not isinstance(policy_id, str) or not isinstance(predicate, str):
            raise LibraryRejected("pack policy is malformed")
        if not isinstance(title, str) or not title.strip():
            raise LibraryRejected("pack policy has no title")
        kind = _predicate_kind(predicate)
        flags = tuple(
            name for name in _predicate_names(predicate) if name in ANSWER_FLAGS
        )
        specs.append(
            BlockSpec(
                block_id=policy_id,
                title=title.strip(),
                kind=kind,
                predicate=predicate,
                question_flags=flags,
                placeholder_key=None,
                pack_heading=None,
                controllable=kind == "disclosure",
                parent="N1_POLICIES",
            )
        )
    return tuple(specs)


def _plain_title(raw: object, code: str) -> str:
    if isinstance(raw, str):
        text = raw.strip()
        if ". " in text and text.split(".", 1)[0].isdigit():
            return text.split(". ", 1)[1]
        if text:
            return text
    return code


def _note_templates(directory: object) -> dict[str, dict[str, object]]:
    from pathlib import Path

    notes_dir = Path(str(directory)) / "notes"
    templates: dict[str, dict[str, object]] = {}
    for path in sorted(notes_dir.glob("*.json")):
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            templates[path.stem] = loaded
    return templates


def _load_policies() -> tuple[dict[str, object], ...]:
    path = pack_dir() / "policies.py"
    spec = importlib.util.spec_from_file_location("findraft_note_library_policies", path)
    if spec is None or spec.loader is None:
        raise LibraryRejected("pack policies are missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    policies = getattr(module, "POLICIES", None)
    if not isinstance(policies, list):
        raise LibraryRejected("pack policies are missing")
    typed: list[dict[str, object]] = []
    for item in policies:
        if not isinstance(item, dict):
            raise LibraryRejected("pack policy is malformed")
        typed.append(item)
    return tuple(typed)


@lru_cache(maxsize=1)
def _questions() -> dict[str, str]:
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
                found[flag] = question.strip()
    extra = json.loads(
        (directory / "disclosure-questions.json").read_text(encoding="utf-8")
    )
    questions = extra.get("questions") if isinstance(extra, dict) else None
    if isinstance(questions, list):
        for item in questions:
            if not isinstance(item, dict):
                continue
            flag = item.get("flag")
            question = item.get("question")
            if isinstance(flag, str) and isinstance(question, str) and question.strip():
                found[flag] = question.strip()
    return found


@lru_cache(maxsize=1)
def _reason_labels() -> dict[str, str]:
    loaded = json.loads(
        (pack_dir() / "reason-labels.json").read_text(encoding="utf-8")
    )
    if not isinstance(loaded, dict):
        raise LibraryRejected("reason labels are missing")
    labels: dict[str, str] = {}
    for key, value in loaded.items():
        if isinstance(key, str) and isinstance(value, str):
            labels[key] = value
    return labels
