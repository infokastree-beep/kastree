"""Regressions for the v6.8 verification findings (chart v2 wiring)."""
import importlib.util as ilu
import json
import pathlib
import unittest
from decimal import Decimal as D

from engine.mapping import aggregate, suggest_mapping
from engine.notes import build_note_context, select_notes
from engine.reconciliation import check_bs_balances
from engine.schemas import TBLine
from engine.statements import build_sofp

PACK = pathlib.Path(__file__).resolve().parent.parent / "content" / "frs102-1a-ie" / "2024.09"
NOTES = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (PACK / "notes").glob("*.json")}
_spec = ilu.spec_from_file_location("md", str(PACK / "mapping-defaults.py"))
MD = ilu.module_from_spec(_spec)
_spec.loader.exec_module(MD)


def mapped(bal: dict) -> dict:
    lines, maps = [], {}
    for i, (k, v) in enumerate(bal.items()):
        code, v = str(9000 + i), D(v)
        lines.append(TBLine(code, k, v if v > 0 else D("0"), -v if v < 0 else D("0")))
        maps[code] = k
    return aggregate(lines, maps)


class TestChartV2Balances(unittest.TestCase):
    def _check(self, bal: dict, net: str) -> None:
        s = build_sofp(mapped(bal), {})
        self.assertTrue(check_bs_balances(s).passed)
        self.assertTrue(s["articulates"])
        self.assertEqual(s["net_assets"], D(net))

    def test_provisions_reduce_net_assets(self):
        self._check({"CASH": "30000", "PROVISIONS": "-10000", "SHARE_CAPITAL": "-100",
                     "RETAINED_EARNINGS": "-19900"}, "20000")

    def test_deferred_tax_liability_reduces_net_assets(self):
        self._check({"CASH": "30000", "DEFERRED_TAX": "-5000", "SHARE_CAPITAL": "-100",
                     "RETAINED_EARNINGS": "-24900"}, "25000")

    def test_share_premium_is_equity(self):
        self._check({"CASH": "30000", "SHARE_PREMIUM": "-5000", "SHARE_CAPITAL": "-100",
                     "RETAINED_EARNINGS": "-24900"}, "30000")


class TestNotesSeeChartV2(unittest.TestCase):
    def test_vat_paye_and_fixtures_trigger_their_notes(self):
        m = mapped({"CASH": "40000", "DIRECTOR_LOAN": "50000", "FA_FIXTURES_COST": "12000",
                    "VAT_CONTROL": "-21500", "PAYE_PRSI": "-8300", "SHARE_CAPITAL": "-100",
                    "RETAINED_EARNINGS": "-72100"})
        ctx = build_note_context(m, NOTES)
        self.assertEqual(ctx["CREDITORS"], D("29800"))
        self.assertEqual(ctx["FIXED_ASSETS_NBV"], D("12000"))
        self.assertTrue({"N2_FA", "N4_CREDITORS"} <= set(select_notes(NOTES, ctx)))


class TestChartV2Mapping(unittest.TestCase):
    @staticmethod
    def _map(name: str):
        class L:
            nominal_code = "9901"
            account_name = name
        return suggest_mapping(L(), {}, MD.KEYWORD_SCORES, MD.CODE_RANGES)[0]

    def test_pl_wording_never_suggests_chart_v2_balance_sheet_lines(self):
        for name in ["Deferred tax charge", "Director's loan interest",
                     "VAT on purchases written off"]:
            with self.subTest(name=name):
                self.assertNotIn(self._map(name), {"DEFERRED_TAX", "DIRECTOR_LOAN", "VAT_CONTROL"})

    def test_hire_purchase_and_finance_lease_map_to_presentable_lines(self):
        self.assertEqual(self._map("Hire purchase creditor"), "LOANS_GT1Y")
        self.assertEqual(self._map("Finance lease creditor"), "LEASE_LIABILITY_GT1Y")


if __name__ == "__main__":
    unittest.main()
