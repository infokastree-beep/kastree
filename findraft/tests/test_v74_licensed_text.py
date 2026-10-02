"""Corrections made against the licensed FRS 102 (September 2024) text in v7.4."""
import importlib.util as ilu
import json
import pathlib
import unittest

from engine.mapping import aggregate
from engine.statements import SOFP_COMPLIANCE_STATEMENT, build_sofp
from tests.fixtures import MAPPINGS, tb_lines

PACK = pathlib.Path(__file__).resolve().parent.parent / "content" / "frs102-1a-ie" / "2024.09"


def _load(name):
    spec = ilu.spec_from_file_location(name, str(PACK / f"{name}.py"))
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLicensedTextCorrections(unittest.TestCase):
    def test_sofp_carries_the_1a6a_statement_from_one_wording(self):
        # FRS 102 1A.6A; Ireland: s.324(4A) Companies Act 2014
        s = build_sofp(aggregate(tb_lines(), MAPPINGS), {})
        self.assertEqual(s["compliance_statement"], SOFP_COMPLIANCE_STATEMENT)
        self.assertEqual(_load("statements").SOFP_COMPLIANCE_STATEMENT, SOFP_COMPLIANCE_STATEMENT)

    def test_deferred_tax_policy_follows_section_29(self):
        body = next(p["body"] for p in _load("policies").POLICIES if p["id"] == "TAXATION")
        self.assertIn("all timing differences", body)        # 29.6
        self.assertNotIn("crystallise", body)                 # old partial-provision test
        self.assertIn("not discounted", body)                 # 29.17

    def test_no_checklist_reference_is_unverified(self):
        items = json.loads((PACK / "disclosure-checklist.json").read_text(encoding="utf-8"))["items"]
        unverified = [i["id"] for i in items if not i["statuteRefStatus"].startswith("verified")]
        self.assertEqual(unverified, [])
        no_cite = sorted(i["id"] for i in items if "no explicit statute cite" in i["statuteRefStatus"])
        self.assertEqual(no_cite, ["1AD.1", "1AD.41"])


if __name__ == "__main__":
    unittest.main()
