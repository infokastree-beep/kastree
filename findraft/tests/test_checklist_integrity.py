"""Locks the disclosure checklist's verification labels to what the data supports."""
import json
import re
import unittest
import pathlib

PACK = pathlib.Path(__file__).resolve().parent.parent / "content" / "frs102-1a-ie" / "2024.09"
ALLOWED = {
    "verified-vs-sept2024-pdf",
    "verified-vs-sept2024-pdf (no explicit statute cite in text)",
    "authored-reference PENDING qualified verification",
    "requirement-verified-vs-sept2024-pdf; citation pending",
}


class TestChecklistIntegrity(unittest.TestCase):
    def test_every_verified_item_carries_source_location(self):
        """v6.3: every item claiming 'verified' status must carry an evidence
        record — licensed-PDF page and an exact quoted phrase. No evidence,
        no 'verified' claim. Applies to all verified items, including the
        restored 1AD.3/1AD.4/1AD.6."""
        cl = json.loads((PACK / "disclosure-checklist.json").read_text())
        for item in cl["items"]:
            status = item.get("statuteRefStatus", "")
            if not status.startswith("verified"):
                continue
            ev = item.get("evidence")
            self.assertIsNotNone(ev, f"{item['id']} claims '{status}' but has no evidence record")
            self.assertIsInstance(ev.get("licensed_pdf_page"), int, f"{item['id']} evidence has no page")
            self.assertGreater(ev["licensed_pdf_page"], 0)
            quote = ev.get("quote", "")
            self.assertGreaterEqual(len(quote), 40, f"{item['id']} evidence quote too short")
            if "no explicit statute cite" not in status:
                tok = re.search(r"(\d+\(\d+[a-zA-Z]?\))", item.get("statuteRef", "")) \
                    or re.search(r"\bs\.(\d+[A-Za-z]?(?:\(\d+\))?)", item.get("statuteRef", "")) \
                    or re.search(r"paras? (\d+)", item.get("statuteRef", ""))
                if tok:
                    self.assertIn(tok.group(1), quote,
                        f"{item['id']} quote does not contain its cited reference {tok.group(1)}")

    def test_statuses_and_references_are_well_formed(self):
        items = json.loads((PACK / "disclosure-checklist.json").read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(items), 55)
        for it in items:
            with self.subTest(item=it["id"]):
                self.assertIn(it["statuteRefStatus"], ALLOWED)
                ref = it["statuteRef"]
                self.assertTrue(ref)
                self.assertFalse(it["topic"].startswith(ref), "reference is truncated topic text")
                self.assertNotIn("Sch3A", ref, "malformed schedule prefix")


if __name__ == "__main__":
    unittest.main()
