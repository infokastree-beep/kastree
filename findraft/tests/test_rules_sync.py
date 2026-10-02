"""findraft.mdc must be .cursorrules plus a header scoping it to findraft/**."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestRulesSync(unittest.TestCase):
    def test_mdc_is_scoped_copy_of_cursorrules(self):
        mdc = (ROOT / "findraft.mdc").read_text(encoding="utf-8")
        rules = (ROOT / ".cursorrules").read_text(encoding="utf-8")
        self.assertTrue(mdc.startswith("---\n"))
        header, body = mdc[4:].split("\n---\n", 1)
        self.assertIn("globs: findraft/**", header.splitlines())
        self.assertIn("alwaysApply: false", header.splitlines())
        self.assertEqual(body, rules)


if __name__ == "__main__":
    unittest.main()
