"""ISO 3166-1 English short names, used only to display a stored code.

Saving a country still uses the company-form rule: blank, or two letters.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "data" / "countries.json"


@cache
def country_names() -> dict[str, str]:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("country list is unreadable")
    names: dict[str, str] = {}
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("country list is unreadable")
        code = row.get("code")
        name = row.get("name")
        if (
            not isinstance(code, str)
            or not isinstance(name, str)
            or len(code) != 2
            or not code.isalpha()
            or not code.isupper()
        ):
            raise ValueError("country list is unreadable")
        names[code] = name
    return names


def country_label(code: str | None) -> str:
    """English name when the code is listed, otherwise the code itself."""
    if code is None:
        return ""
    text = code.strip().upper()
    if text == "":
        return ""
    return country_names().get(text, text)
