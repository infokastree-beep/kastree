"""Company legal form codes and Companies Act 2014 name suffixes.

The pack object ``company_legal_forms`` is the list. Its source status is
researched from the public Act. A blank choice stores NULL. Codes are stored,
not free text.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import append_audit_log
from findraft.engine.pack import pack_dir

_PACK_ID = "frs102-1a-ie"
_PACK_VERSION = "2024.09"
_PASS = "The company name ends with a legal-form suffix."

MissingSuffix = Literal["blocker", "notice"]


@dataclass(frozen=True)
class LegalFormRule:
    code: str
    name: str
    provision: str
    suffixes: tuple[str, ...]
    missing_suffix: MissingSuffix
    notice_provision: str | None = None
    directors_provision: str | None = None
    minimum_directors: int | None = None


# Used only when the pack file cannot be read. The test locks this to the pack.
_FALLBACK: tuple[LegalFormRule, ...] = (
    LegalFormRule(
        "ltd",
        "Private company limited by shares",
        "Companies Act 2014, section 26",
        ("Limited", "Ltd", "Teoranta", "Teo"),
        "blocker",
    ),
    LegalFormRule(
        "dac",
        "Designated activity company",
        "Companies Act 2014, section 969",
        (
            "Designated Activity Company",
            "Cuideachta Ghníomhaíochta Ainmnithe",
            "d.a.c.",
            "DAC",
            "c.g.a.",
            "CGA",
        ),
        "notice",
        notice_provision="Companies Act 2014, section 971",
        directors_provision="Companies Act 2014, section 985",
        minimum_directors=2,
    ),
    LegalFormRule(
        "plc",
        "Public limited company",
        "Companies Act 2014, section 1008",
        (
            "public limited company",
            "cuideachta phoiblí theoranta",
            "p.l.c.",
            "plc",
            "c.p.t.",
            "cpt",
        ),
        "blocker",
    ),
    LegalFormRule(
        "clg",
        "Company limited by guarantee",
        "Companies Act 2014, section 1178",
        (
            "company limited by guarantee",
            "cuideachta faoi theorainn ráthaíochta",
            "c.l.g.",
            "clg",
            "c.t.r.",
            "ctr",
        ),
        "blocker",
    ),
    LegalFormRule(
        "ulc",
        "Private unlimited company",
        "Companies Act 2014, sections 1228 and 1237",
        ("unlimited company", "cuideachta neamhtheoranta", "u.c.", "uc", "c.n.", "cn"),
        "blocker",
    ),
    LegalFormRule(
        "puc",
        "Public unlimited company",
        "Companies Act 2014, sections 1228 and 1237",
        ("unlimited company", "cuideachta neamhtheoranta", "u.c.", "uc", "c.n.", "cn"),
        "blocker",
    ),
    LegalFormRule(
        "pulc",
        "Public unlimited company with no share capital",
        "Companies Act 2014, sections 1228 and 1237",
        ("unlimited company", "cuideachta neamhtheoranta", "u.c.", "uc", "c.n.", "cn"),
        "blocker",
    ),
)


def legal_form_rules() -> tuple[LegalFormRule, ...]:
    """Pack list, or the researched fallback when the file cannot be read."""
    try:
        raw = json.loads(
            (pack_dir(_PACK_ID, _PACK_VERSION) / "pack.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError):
        return _FALLBACK
    payload = raw.get("company_legal_forms") if isinstance(raw, dict) else None
    forms = payload.get("forms") if isinstance(payload, dict) else None
    if not isinstance(forms, list):
        return _FALLBACK
    parsed: list[LegalFormRule] = []
    for item in forms:
        rule = _parse_rule(item)
        if rule is None:
            return _FALLBACK
        parsed.append(rule)
    if not parsed:
        return _FALLBACK
    return tuple(parsed)


def legal_form_codes() -> frozenset[str]:
    return frozenset(rule.code for rule in legal_form_rules())


def legal_form_code(value: object) -> str | None:
    """A listed code, or none when the field is blank."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Legal form must be one of the listed company types.")
    text = value.strip().lower()
    if text == "":
        return None
    if text not in legal_form_codes():
        raise ValueError("Legal form must be one of the listed company types.")
    return text


def rule_for(code: str | None) -> LegalFormRule | None:
    if code is None:
        return None
    folded = code.strip().lower()
    for rule in legal_form_rules():
        if rule.code == folded:
            return rule
    return None


def name_has_suffix(name: str, suffixes: tuple[str, ...]) -> bool:
    """True when the name ends with one listed suffix. A final period is optional."""
    text = " ".join(name.strip().casefold().split())
    for suffix in suffixes:
        token = " ".join(suffix.strip().casefold().split())
        if token == "":
            continue
        candidates = [text]
        if text.endswith(".") and not token.endswith("."):
            candidates.append(text[:-1].rstrip())
        for candidate in candidates:
            if candidate == token or candidate.endswith(" " + token):
                return True
    return False


def suffix_list(suffixes: tuple[str, ...]) -> str:
    items = list(suffixes)
    if len(items) == 1:
        return items[0]
    if not items:
        return ""
    return f"{', '.join(items[:-1])}, or {items[-1]}"


def missing_suffix_message(suffixes: tuple[str, ...]) -> str:
    return f"The company name does not end with {suffix_list(suffixes)}."


def dac_suffix_notice(name: str, rule: LegalFormRule) -> str | None:
    """Section 971 exemption: a missing DAC suffix is a notice, not a blocker."""
    if rule.missing_suffix != "notice" or name_has_suffix(name, rule.suffixes):
        return None
    provision = rule.notice_provision or "Companies Act 2014, section 971"
    return (
        "The company is recorded as a designated activity company and the name "
        f"does not end with {suffix_list(rule.suffixes)}. "
        f"{provision} provides an exemption from that suffix, so this is a notice."
    )


def dac_director_notice(director_count: int, rule: LegalFormRule) -> str | None:
    """Section 985: a DAC has at least two directors. This does not block."""
    minimum = rule.minimum_directors
    if minimum is None or director_count >= minimum:
        return None
    provision = rule.directors_provision or "Companies Act 2014, section 985"
    return (
        "The company is recorded as a designated activity company and fewer "
        f"than {minimum} directors are recorded. "
        f"{provision} requires at least {minimum} directors."
    )


def passing_suffix_message() -> str:
    return _PASS


async def record_legal_form_change(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    company_id: uuid.UUID,
    previous: str | None,
    current: str | None,
) -> None:
    """Who and when. The values are codes, never amounts."""
    if previous == current:
        return
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="company_legal_form_set",
        entity_type="company",
        entity_id=company_id,
        old_value={"legal_form": previous},
        new_value={"legal_form": current},
    )


def _parse_rule(item: object) -> LegalFormRule | None:
    if not isinstance(item, dict):
        return None
    code = item.get("code")
    name = item.get("name")
    provision = item.get("provision")
    suffixes = item.get("suffixes")
    missing = item.get("missing_suffix")
    if (
        not isinstance(code, str)
        or not isinstance(name, str)
        or not isinstance(provision, str)
        or missing not in {"blocker", "notice"}
        or not isinstance(suffixes, list)
        or not suffixes
        or not all(isinstance(suffix, str) and suffix.strip() for suffix in suffixes)
    ):
        return None
    notice = item.get("notice_provision")
    directors = item.get("directors_provision")
    minimum = item.get("minimum_directors")
    if notice is not None and not isinstance(notice, str):
        return None
    if directors is not None and not isinstance(directors, str):
        return None
    if minimum is not None and (
        isinstance(minimum, bool) or not isinstance(minimum, int)
    ):
        return None
    kind: MissingSuffix = "notice" if missing == "notice" else "blocker"
    return LegalFormRule(
        code.strip().lower(),
        name.strip(),
        provision.strip(),
        tuple(suffix.strip() for suffix in suffixes),
        kind,
        notice_provision=None if notice is None else notice.strip(),
        directors_provision=None if directors is None else directors.strip(),
        minimum_directors=minimum,
    )
