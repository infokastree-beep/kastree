"""Spec §7.8 doctored rows, encoded exactly as the document describes them."""
import unittest
from decimal import Decimal as Dec
from tests.fixtures import RULES, MAPPINGS, tb_lines
from engine.mapping import aggregate
from engine.reconciliation import review_rules

PROFIT = Dec("157650")


def codes(mapped, descriptions=None):
    return [h.code for h in review_rules(mapped, descriptions or {}, PROFIT, pack_path=RULES)]


class TestDoctoredRows(unittest.TestCase):
    def test_negative_expense_line(self):
        self.assertEqual(codes({"ADMIN_EXPENSES": Dec("-3200")}), ["R-NEG-001"])

    def test_round_number_expense_line(self):
        self.assertEqual(codes({"ADMIN_EXPENSES": Dec("50000")}), ["R-RND-001"])

    def test_large_director_line(self):
        m = aggregate(tb_lines(), MAPPINGS)
        m["OTHER_CREDITORS"] -= Dec("7800")
        m["CASH"] += Dec("7800")
        self.assertEqual(codes(m, {"OTHER_CREDITORS": "Director loan account"}), ["R-DIR-001"])

    def test_missing_depreciation(self):
        m = aggregate(tb_lines(), MAPPINGS)
        del m["DEPRECIATION_CHARGE"]
        self.assertEqual(codes(m), ["R-DEP-001"])


if __name__ == "__main__":
    unittest.main()
