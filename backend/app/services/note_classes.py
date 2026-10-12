"""Note classes from the pinned pack. Display only. No calculation."""

from __future__ import annotations

import json
from functools import lru_cache

from findraft.engine.pack import pack_dir


@lru_cache(maxsize=1)
def note_class_order() -> tuple[str, ...]:
    """Class ids in pack order. ``other`` is the unclassified bucket."""
    loaded = json.loads((pack_dir() / "pack.json").read_text(encoding="utf-8"))
    raw = loaded.get("note_classes") if isinstance(loaded, dict) else None
    if not isinstance(raw, list) or not raw:
        raise ValueError("pack note classes are missing")
    order: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip() or item in order:
            raise ValueError("pack note classes are malformed")
        order.append(item)
    if "other" not in order:
        raise ValueError("pack note classes are missing other")
    return tuple(order)


@lru_cache(maxsize=1)
def classes_by_code() -> dict[str, str]:
    """Each note file's class. A missing class is other."""
    allowed = set(note_class_order())
    found: dict[str, str] = {}
    for path in sorted((pack_dir() / "notes").glob("*.json")):
        loaded = json.loads(path.read_text(encoding="utf-8"))
        raw = loaded.get("class") if isinstance(loaded, dict) else None
        if raw is None:
            found[path.stem] = "other"
            continue
        if not isinstance(raw, str) or raw not in allowed:
            raise ValueError(f"note {path.stem} has an unknown class")
        found[path.stem] = raw
    return found


def note_class_for(code: str) -> str:
    return classes_by_code().get(code, "other")


def class_label(value: str) -> str:
    text = value.strip()
    if not text:
        return "Other"
    return text[:1].upper() + text[1:]
