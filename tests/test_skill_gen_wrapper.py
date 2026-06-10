"""
Smoke test for the `skill-gen` executable wrapper at the repo root.

cli.py's own "Next step" hints and `skill-gen doctor`'s suggested commands
are written as `skill-gen <subcommand> ...`. This test confirms the wrapper
script actually dispatches to tools.skill_generator.cli.main so those hints
are runnable as printed.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "skill-gen"


class TestSkillGenWrapper(unittest.TestCase):
    def test_version_matches_cli_module(self):
        wrapper = subprocess.run(
            [sys.executable, str(WRAPPER), "--version"],
            capture_output=True, text=True, check=True,
        )
        module = subprocess.run(
            [sys.executable, "-m", "tools.skill_generator.cli", "--version"],
            capture_output=True, text=True, check=True, cwd=str(REPO_ROOT),
        )
        self.assertEqual(wrapper.stdout, module.stdout)
        self.assertTrue(wrapper.stdout.startswith("skill-gen "))

    def test_doctor_subcommand_runs_through_wrapper(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "src").mkdir()
            (repo / "src" / "Foo.java").write_text(
                "public class Foo {}", encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(WRAPPER), "doctor", str(repo)],
                capture_output=True, text=True, check=True,
            )
            self.assertIn("Java classes", result.stdout)

    def test_is_executable(self):
        self.assertTrue(WRAPPER.exists())
        self.assertTrue(WRAPPER.stat().st_mode & 0o111, "skill-gen should be executable")


if __name__ == "__main__":
    unittest.main()
