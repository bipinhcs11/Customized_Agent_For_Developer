"""
Tests for tools.skill_generator.doctor — the pre-flight diagnostic command.

These tests build small synthetic Java repos in tempdirs, run the diagnose
function, and check that the report has the right shape and content. The
human-readable formatter is checked for the friendly tone (no AGENT.md-isms
leaking into the user-facing output) and the JSON formatter is checked for
parseability.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.skill_generator.doctor import diagnose, format_human, format_json


def _write(repo: Path, rel: str, content: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _tiny_spring_boot_repo(td: str) -> Path:
    repo = Path(td)
    _write(repo, "pom.xml", "<project><properties><java.version>17</java.version></properties></project>")
    _write(repo, "src/main/java/com/acme/foo/FooController.java",
           "package com.acme.foo;\n@RestController\npublic class FooController { void get() {} }")
    _write(repo, "src/main/java/com/acme/foo/FooService.java",
           "package com.acme.foo;\npublic class FooService { void process() {} }")
    _write(repo, "src/main/java/com/acme/bar/BarController.java",
           "package com.acme.bar;\n@RestController\npublic class BarController { void list() {} }")
    _write(repo, "src/main/resources/application.yml",
           "app:\n  foo:\n    enabled: true\n")
    return repo


class TestDiagnoseHappyPath(unittest.TestCase):
    def test_returns_a_complete_report(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _tiny_spring_boot_repo(td)
            report = diagnose(repo)

            self.assertIn("totals", report)
            self.assertIn("stack", report)
            self.assertIn("effort", report)
            self.assertEqual(report["totals"]["java_classes"], 3)
            self.assertEqual(report["totals"]["config_files"], 1)
            # Two top-level packages (com.acme.foo, com.acme.bar) → 1 if grouped
            # by top-two levels; our code uses ".".join(parts[:2]) so foo+bar
            # both collapse to "com.acme".
            self.assertEqual(report["estimated_domains"], 1)

    def test_detects_framework_and_build_system(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _tiny_spring_boot_repo(td)
            report = diagnose(repo)
            # Build system from pom.xml
            self.assertEqual(report["stack"]["build_system"], "Maven")
            # No @SpringBootApplication, but @RestController is enough to be
            # detected as Spring MVC by the existing heuristic.
            self.assertIn(report["stack"]["framework"],
                          ("Spring Boot", "Spring MVC", "Unknown"))

    def test_effort_estimate_is_reasonable(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _tiny_spring_boot_repo(td)
            report = diagnose(repo)
            # plan + N + link = at least 3 turns
            self.assertGreaterEqual(report["effort"]["host_agent_turns"], 3)
            self.assertGreater(report["effort"]["estimated_minutes"], 0)


class TestDiagnoseEdgeCases(unittest.TestCase):
    def test_empty_repo_returns_zero_java(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _write(repo, "README.md", "no java here")
            report = diagnose(repo)
            self.assertEqual(report["totals"]["java_classes"], 0)

    def test_default_package_classes_bumped(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _write(repo, "src/Main.java", "public class Main {}")
            report = diagnose(repo)
            self.assertEqual(report["default_package_count"], 1)
            # Default-package adds one "domain"
            self.assertGreaterEqual(report["estimated_domains"], 1)

    def test_god_class_surfaced(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            big = "package x;\npublic class Big {\n" + ("  void m() {}\n" * 350) + "}\n"
            _write(repo, "src/main/java/x/Big.java", big)
            report = diagnose(repo)
            self.assertTrue(any(g["class_name"] == "Big" for g in report["god_classes"]))


class TestFormatHumanFriendliness(unittest.TestCase):
    """The whole point of doctor is to be readable. These tests verify that
    the output does not leak internal jargon and DOES tell the developer the
    things they need to know."""

    def test_includes_friendly_signposts(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _tiny_spring_boot_repo(td)
            out = format_human(diagnose(repo))
            self.assertIn("== Looking at ", out)
            self.assertIn("Java classes", out)
            self.assertIn("How long this will take", out)
            self.assertIn("Suggested first step", out)
            self.assertIn("paste-and-save", out)

    def test_does_not_leak_internal_jargon(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _tiny_spring_boot_repo(td)
            out = format_human(diagnose(repo))
            for bad in ("artifact-2", "artifact-3", "_collect_source_blob",
                        "configKeys", "PHASE_2_UPDATE_PROMPT_PREFIX"):
                self.assertNotIn(bad, out, f"output leaks internal jargon: {bad}")

    def test_empty_repo_says_so_clearly(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _write(repo, "README.md", "no java")
            out = format_human(diagnose(repo))
            self.assertIn("No Java files found", out)
            # The empty-repo path stops early — don't render effort/steps for
            # a repo we can't process.
            self.assertNotIn("Suggested first step", out)

    def test_god_class_warning_only_when_needed(self):
        # A small clean repo should NOT show the "very large files" warning.
        with tempfile.TemporaryDirectory() as td:
            repo = _tiny_spring_boot_repo(td)
            out = format_human(diagnose(repo))
            self.assertNotIn("very large", out)


class TestFormatJson(unittest.TestCase):
    def test_output_is_parseable(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _tiny_spring_boot_repo(td)
            report = diagnose(repo)
            out = format_json(report)
            reloaded = json.loads(out)
            self.assertEqual(reloaded["totals"], report["totals"])


if __name__ == "__main__":
    unittest.main()
