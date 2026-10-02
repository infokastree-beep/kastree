"""Pack completeness test — asserts every Appendix D disclosure item (1AD.1-1AD.55)
maps to a note template, an engine feature, or a documented N/A path."""
import json, pathlib
try:
    import pytest  # noqa: F401 (optional; plain asserts run under unittest too)
except ImportError:
    pytest = None

PACK = pathlib.Path(__file__).parent
NOTES = {p.stem: json.loads(p.read_text()) for p in (PACK/"notes").glob("*.json")}

def test_all_appendixD_items_covered():
    cl = json.loads((PACK/"disclosure-checklist.json").read_text())
    items = cl["items"]
    assert len(items) == 55, f"expected 55 items, got {len(items)}"
    for it in items:
        note = it.get("note")
        if note in (None, "_engine", "_line_level"):
            continue  # engine-handled or format-level
        assert note in NOTES, f"{it['id']} mapped to missing note {note}"
        assert it["id"] in NOTES[note]["sourceRef"], \
            f"{it['id']} not cited in {note}.sourceRef"

def test_every_note_cites_appendixD():
    for code, tpl in NOTES.items():
        for ref in tpl["sourceRef"]:
            assert ref.startswith("1AD.") or ref.startswith("1A."), code

def test_every_note_has_includeWhen():
    for code, tpl in NOTES.items():
        assert "includeWhen" in tpl and tpl["includeWhen"], code

def test_required_fields_present():
    req = ["title","sourceRef","jurisdiction","bodyTemplate"]
    for code in ["N1_POLICIES","N2_FA","N4_CREDITORS"]:
        for k in req:
            assert k in NOTES[code], f"{code} missing {k}"
