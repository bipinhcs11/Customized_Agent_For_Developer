"""
Regression test for tools.skill_generator.update._domain_from_skill.

Before the fix, `classes` was built with `list(set(...))`, producing a
non-deterministic ordering across Python processes (PYTHONHASHSEED varies).
The fix uses `sorted(set(...))` so the list is always alphabetical.

Stdlib-only (no pytest).
"""
import unittest

from tools.skill_generator.update import _domain_from_skill


class TestDomainFromSkillOrdering(unittest.TestCase):
    def test_class_names_sorted_alphabetically(self):
        """classes list must be sorted so two calls return identical output."""
        md = (
            "ZebraController.java handles Z.\n"
            "AppleService.java handles A.\n"
            "MangoDao.java handles M.\n"
        )
        domain = _domain_from_skill(md, "mixed")
        self.assertEqual(domain["classes"], ["AppleService", "MangoDao", "ZebraController"])

    def test_repeated_calls_produce_identical_classes_list(self):
        """Two calls with the same input must return the same list (no hash randomness)."""
        md = (
            "ZebraController.java handles Z.\n"
            "AppleService.java handles A.\n"
            "MangoDao.java handles M.\n"
        )
        first = _domain_from_skill(md, "x")["classes"]
        second = _domain_from_skill(md, "x")["classes"]
        self.assertEqual(first, second)

    def test_duplicate_class_names_deduplicated_then_sorted(self):
        md = "ZebraService.java appeared once.\nZebraService.java appeared twice.\nAlphaService.java.\n"
        domain = _domain_from_skill(md, "x")
        self.assertEqual(domain["classes"].count("ZebraService"), 1)
        self.assertEqual(domain["classes"][0], "AlphaService")


if __name__ == "__main__":
    unittest.main()
