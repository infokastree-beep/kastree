"""Rounding-flag engine (Accurri behaviour A3, spec §4.6).
Renderer compares sum(rounded children) to rounded total per row; any gap
is flagged amber and deep-links to the chart of accounts."""
from decimal import Decimal as Dec, ROUND_HALF_UP
from urllib.parse import urlencode
from .money import D

def round_to(value, unit) -> Dec:
    unit = D(unit)
    return (D(value) / unit).quantize(Dec("1"), rounding=ROUND_HALF_UP) * unit

def rounding_gap(children_raw: list, total_raw, unit) -> Dec:
    """Positive = children exceed total; negative = children short of total."""
    children_r = sum((round_to(c, unit) for c in children_raw), Dec("0"))
    return children_r - round_to(total_raw, unit)

def flag_for_note(children_raw: list, total_raw, unit, statement_line_id: str) -> dict:
    gap = rounding_gap(children_raw, total_raw, unit)
    if gap == 0:
        return {"flagged": False, "gap": gap, "deeplink": None}
    return {"flagged": True, "gap": gap,
            "deeplink": "/mapping?" + urlencode({"rounding": statement_line_id,
                                                 "diff": str(gap)})}
