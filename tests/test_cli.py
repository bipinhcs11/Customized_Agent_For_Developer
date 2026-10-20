"""
Smoke tests for tools.skill_generator.cli — parser wiring.

Verifies that all nine documented subcommands exist and their flags are
registered correctly. No subprocess calls, no file I/O — pure argparse
inspection. Running these prevents silent regressions where a flag rename
in one module isn't propagated to the CLI.

Covers:
  build_parser registration
      - all nine subcommands are present: crawl, plan-emit, plan-ingest,
        generate-emit, generate-ingest, link-emit, link-ingest,
        update-emit, update-ingest, validate, doctor
      - --version and --help exit cleanly (SystemExit(0))
      - an unknown subcommand exits non-zero

  crawl
      - parses positional `path`
      - --exclude is repeatable (append action)
      - --skip-tests / --compact are boolean flags
      - --output sets args.output

  plan-emit / plan-ingest
      - positional `index` / `response` are captured
      - optional --output works

  generate-emit / generate-ingest
      - positional `plan` + required --repo work
      - --only is repeatable (append action)
      - --force and --no-validate are boolean flags

  link-emit / link-ingest
      - positional `skills_dir` / `response` and required --skills-dir work

  update-emit / update-ingest
      - --repo defaults to "."
      - --base defaults to "HEAD~1", --head to "HEAD"
      - --feature is optional
      - --commit is a boolean flag

  validate / doctor
      - validate accepts multiple paths (nargs="+")
      - doctor accepts positional path and --json flag

All tests use stdlib only (argparse, unittest).
"""
from __future__ import annotations

import argparse
import sys
import unittest

from tools.skill_generator.cli import build_parser
from tools.skill_generator.crawler import TOOL_VERSION


class TestParserCreation(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_parser_is_argumentparser(self):
        self.assertIsInstance(self.parser, argparse.ArgumentParser)

    def test_prog_is_skill_gen(self):
        self.assertEqual(self.parser.prog, "skill-gen")

    def test_version_exits_zero(self):
        with self.assertRaises(SystemExit) as cm:
            self.parser.parse_args(["--version"])
        self.assertEqual(cm.exception.code, 0)

    def test_help_exits_zero(self):
        with self.assertRaises(SystemExit) as cm:
            self.parser.parse_args(["--help"])
        self.assertEqual(cm.exception.code, 0)

    def test_unknown_subcommand_exits_nonzero(self):
        with self.assertRaises(SystemExit) as cm:
            self.parser.parse_args(["does-not-exist"])
        self.assertNotEqual(cm.exception.code, 0)

    def test_no_subcommand_exits_nonzero(self):
        with self.assertRaises(SystemExit) as cm:
            self.parser.parse_args([])
        self.assertNotEqual(cm.exception.code, 0)


class TestAllSubcommands(unittest.TestCase):
    """Every subcommand listed in the module docstring must be registered."""

    _SUBCOMMANDS = [
        "crawl",
        "plan-emit",
        "plan-ingest",
        "generate-emit",
        "generate-ingest",
        "link-emit",
        "link-ingest",
        "update-emit",
        "update-ingest",
        "validate",
        "doctor",
    ]

    def setUp(self):
        self.parser = build_parser()

    def _all_registered_subcommands(self) -> set:
        for action in self.parser._subparsers._group_actions:
            if hasattr(action, "_name_parser_map"):
                return set(action._name_parser_map.keys())
        return set()

    def test_all_subcommands_registered(self):
        registered = self._all_registered_subcommands()
        for cmd in self._SUBCOMMANDS:
            self.assertIn(cmd, registered,
                          f"subcommand '{cmd}' is missing from the parser")


class TestCrawlSubcommand(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_path_is_captured(self):
        args = self.parser.parse_args(["crawl", "/my/repo"])
        self.assertEqual(args.path, "/my/repo")

    def test_output_flag(self):
        args = self.parser.parse_args(["crawl", "/repo", "--output", "/tmp/out.json"])
        self.assertEqual(args.output, "/tmp/out.json")

    def test_exclude_is_repeatable(self):
        args = self.parser.parse_args(
            ["crawl", "/repo", "--exclude", "vendor", "--exclude", "generated"]
        )
        self.assertIn("vendor", args.exclude)
        self.assertIn("generated", args.exclude)

    def test_skip_tests_defaults_false(self):
        args = self.parser.parse_args(["crawl", "/repo"])
        self.assertFalse(args.skip_tests)

    def test_skip_tests_flag_sets_true(self):
        args = self.parser.parse_args(["crawl", "/repo", "--skip-tests"])
        self.assertTrue(args.skip_tests)

    def test_compact_defaults_false(self):
        args = self.parser.parse_args(["crawl", "/repo"])
        self.assertFalse(args.compact)

    def test_compact_flag_sets_true(self):
        args = self.parser.parse_args(["crawl", "/repo", "--compact"])
        self.assertTrue(args.compact)


class TestPlanSubcommands(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_plan_emit_index_captured(self):
        args = self.parser.parse_args(["plan-emit", "/repo/.skill-gen/.index.json"])
        self.assertEqual(args.index, "/repo/.skill-gen/.index.json")

    def test_plan_emit_output_optional(self):
        args = self.parser.parse_args(["plan-emit", "/repo/.skill-gen/.index.json"])
        self.assertIsNone(args.output)

    def test_plan_emit_output_flag(self):
        args = self.parser.parse_args(
            ["plan-emit", "/repo/.skill-gen/.index.json", "--output", "/tmp/prompt.md"]
        )
        self.assertEqual(args.output, "/tmp/prompt.md")

    def test_plan_ingest_response_captured(self):
        args = self.parser.parse_args(["plan-ingest", "/tmp/response.md"])
        self.assertEqual(args.response, "/tmp/response.md")

    def test_plan_ingest_output_optional(self):
        args = self.parser.parse_args(["plan-ingest", "/tmp/response.md"])
        self.assertIsNone(args.output)


class TestGenerateSubcommands(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_generate_emit_plan_and_repo_required(self):
        args = self.parser.parse_args(
            ["generate-emit", "/tmp/plan.json", "--repo", "/my/repo"]
        )
        self.assertEqual(args.plan, "/tmp/plan.json")
        self.assertEqual(args.repo, "/my/repo")

    def test_generate_emit_missing_repo_exits_nonzero(self):
        with self.assertRaises(SystemExit) as cm:
            self.parser.parse_args(["generate-emit", "/tmp/plan.json"])
        self.assertNotEqual(cm.exception.code, 0)

    def test_generate_emit_only_is_repeatable(self):
        args = self.parser.parse_args(
            ["generate-emit", "/tmp/plan.json", "--repo", "/r",
             "--only", "file-delivery", "--only", "invoice-compare"]
        )
        self.assertIn("file-delivery", args.only)
        self.assertIn("invoice-compare", args.only)

    def test_generate_ingest_force_defaults_false(self):
        args = self.parser.parse_args(
            ["generate-ingest", "/tmp/plan.json", "--repo", "/r"]
        )
        self.assertFalse(args.force)

    def test_generate_ingest_force_flag_sets_true(self):
        args = self.parser.parse_args(
            ["generate-ingest", "/tmp/plan.json", "--repo", "/r", "--force"]
        )
        self.assertTrue(args.force)

    def test_generate_ingest_no_validate_defaults_false(self):
        args = self.parser.parse_args(
            ["generate-ingest", "/tmp/plan.json", "--repo", "/r"]
        )
        self.assertFalse(args.no_validate)

    def test_generate_ingest_no_validate_flag(self):
        args = self.parser.parse_args(
            ["generate-ingest", "/tmp/plan.json", "--repo", "/r", "--no-validate"]
        )
        self.assertTrue(args.no_validate)


class TestLinkSubcommands(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_link_emit_skills_dir_captured(self):
        args = self.parser.parse_args(["link-emit", "/repo/.github/skills"])
        self.assertEqual(args.skills_dir, "/repo/.github/skills")

    def test_link_ingest_response_and_skills_dir(self):
        args = self.parser.parse_args(
            ["link-ingest", "/tmp/link-response.md", "--skills-dir", "/repo/.github/skills"]
        )
        self.assertEqual(args.response, "/tmp/link-response.md")
        self.assertEqual(args.skills_dir, "/repo/.github/skills")

    def test_link_ingest_missing_skills_dir_exits_nonzero(self):
        with self.assertRaises(SystemExit) as cm:
            self.parser.parse_args(["link-ingest", "/tmp/resp.md"])
        self.assertNotEqual(cm.exception.code, 0)


class TestUpdateSubcommands(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_update_emit_repo_defaults_to_dot(self):
        args = self.parser.parse_args(["update-emit"])
        self.assertEqual(args.repo, ".")

    def test_update_emit_base_defaults_head_tilde_1(self):
        args = self.parser.parse_args(["update-emit"])
        self.assertEqual(args.base, "HEAD~1")

    def test_update_emit_head_defaults_to_HEAD(self):
        args = self.parser.parse_args(["update-emit"])
        self.assertEqual(args.head, "HEAD")

    def test_update_emit_feature_is_optional(self):
        args = self.parser.parse_args(["update-emit"])
        self.assertIsNone(args.feature)

    def test_update_emit_feature_flag_captured(self):
        args = self.parser.parse_args(["update-emit", "--feature", "file-delivery"])
        self.assertEqual(args.feature, "file-delivery")

    def test_update_ingest_commit_defaults_false(self):
        args = self.parser.parse_args(["update-ingest"])
        self.assertFalse(args.commit)

    def test_update_ingest_commit_flag_sets_true(self):
        args = self.parser.parse_args(["update-ingest", "--commit"])
        self.assertTrue(args.commit)

    def test_update_ingest_no_validate_defaults_false(self):
        args = self.parser.parse_args(["update-ingest"])
        self.assertFalse(args.no_validate)


class TestValidateSubcommand(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_validate_single_path(self):
        args = self.parser.parse_args(["validate", "/skills/file-delivery/SKILL.md"])
        self.assertEqual(args.paths, ["/skills/file-delivery/SKILL.md"])

    def test_validate_multiple_paths(self):
        args = self.parser.parse_args(
            ["validate",
             "/skills/file-delivery/SKILL.md",
             "/skills/invoice-compare/SKILL.md"]
        )
        self.assertEqual(len(args.paths), 2)

    def test_validate_requires_at_least_one_path(self):
        with self.assertRaises(SystemExit) as cm:
            self.parser.parse_args(["validate"])
        self.assertNotEqual(cm.exception.code, 0)


class TestDoctorSubcommand(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_doctor_path_captured(self):
        args = self.parser.parse_args(["doctor", "/my/java/repo"])
        self.assertEqual(args.path, "/my/java/repo")

    def test_doctor_json_defaults_false(self):
        args = self.parser.parse_args(["doctor", "/repo"])
        self.assertFalse(args.json)

    def test_doctor_json_flag_sets_true(self):
        args = self.parser.parse_args(["doctor", "/repo", "--json"])
        self.assertTrue(args.json)


if __name__ == "__main__":
    unittest.main()
