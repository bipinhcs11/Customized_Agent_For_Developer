"""
Smoke tests for tools.skill_generator.cli — argument-wiring only.

`cli.py` had zero test coverage. These tests exercise `build_parser()`,
a pure function that builds the argparse tree, to catch wiring regressions
(missing subcommands, dropped flags, wrong defaults, required-arg changes)
without touching the filesystem or dispatching to the `_cmd_*` handlers.

Covers:
  - All 11 documented subcommands are registered, each wired to its
      `_cmd_*` dispatch function via `set_defaults(func=...)`
  - `--version` is wired to TOOL_VERSION
  - Required arguments raise SystemExit (argparse's usage-error behaviour)
      when omitted: crawl PATH, generate-emit --repo, link-ingest --skills-dir
  - Documented defaults survive: update-emit --base/--head, crawl flags,
      generate-ingest/--output-dir, repeatable --exclude/--only lists
  - `main()` dispatches parsed args to the wired `func` and returns its
      integer result (verified with a stubbed handler)

All tests use stdlib only (argparse, contextlib, io, unittest).
"""
import contextlib
import io
import unittest

from tools.skill_generator import cli
from tools.skill_generator.crawler import TOOL_VERSION


# ---------------------------------------------------------------------------
# Subcommand registration
# ---------------------------------------------------------------------------

_EXPECTED_SUBCOMMANDS = {
    "crawl": cli._cmd_crawl,
    "plan-emit": cli._cmd_plan_emit,
    "plan-ingest": cli._cmd_plan_ingest,
    "generate-emit": cli._cmd_generate_emit,
    "generate-ingest": cli._cmd_generate_ingest,
    "link-emit": cli._cmd_link_emit,
    "link-ingest": cli._cmd_link_ingest,
    "update-emit": cli._cmd_update_emit,
    "update-ingest": cli._cmd_update_ingest,
    "validate": cli._cmd_validate,
    "doctor": cli._cmd_doctor,
}


class TestSubcommandsRegistered(unittest.TestCase):
    def setUp(self):
        self.parser = cli.build_parser()
        # argparse stores subparsers under the dest="cmd" action's choices map
        self.subactions = next(
            a for a in self.parser._subparsers._group_actions
            if hasattr(a, "choices")
        )

    def test_all_documented_subcommands_present(self):
        self.assertEqual(set(self.subactions.choices), set(_EXPECTED_SUBCOMMANDS))

    def test_each_subcommand_wired_to_its_handler(self):
        for name, handler in _EXPECTED_SUBCOMMANDS.items():
            with self.subTest(subcommand=name):
                sub_parser = self.subactions.choices[name]
                func = sub_parser.get_default("func")
                self.assertIs(func, handler)

    def test_cmd_dest_required(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args([])


# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------

class TestVersionFlag(unittest.TestCase):
    def test_version_prints_tool_version_and_exits_zero(self):
        parser = cli.build_parser()
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stdout(buf):
                parser.parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn(TOOL_VERSION, buf.getvalue())


# ---------------------------------------------------------------------------
# Required arguments raise SystemExit (argparse usage errors) when omitted
# ---------------------------------------------------------------------------

class TestRequiredArguments(unittest.TestCase):
    def setUp(self):
        self.parser = cli.build_parser()

    def _expect_usage_error(self, argv):
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stderr(buf):
                self.parser.parse_args(argv)
        self.assertEqual(ctx.exception.code, 2)

    def test_crawl_requires_path(self):
        self._expect_usage_error(["crawl"])

    def test_plan_emit_requires_index(self):
        self._expect_usage_error(["plan-emit"])

    def test_plan_ingest_requires_response(self):
        self._expect_usage_error(["plan-ingest"])

    def test_generate_emit_requires_repo_flag(self):
        self._expect_usage_error(["generate-emit", "plan.json"])

    def test_generate_ingest_requires_repo_flag(self):
        self._expect_usage_error(["generate-ingest", "plan.json"])

    def test_link_emit_requires_skills_dir_positional(self):
        self._expect_usage_error(["link-emit"])

    def test_link_ingest_requires_skills_dir_flag(self):
        self._expect_usage_error(["link-ingest", "response.md"])

    def test_validate_requires_at_least_one_path(self):
        self._expect_usage_error(["validate"])

    def test_doctor_requires_path(self):
        self._expect_usage_error(["doctor"])

    def test_unknown_subcommand_rejected(self):
        self._expect_usage_error(["frobnicate"])


# ---------------------------------------------------------------------------
# Documented defaults
# ---------------------------------------------------------------------------

class TestDefaults(unittest.TestCase):
    def setUp(self):
        self.parser = cli.build_parser()

    def test_crawl_defaults(self):
        args = self.parser.parse_args(["crawl", "/repo"])
        self.assertEqual(args.path, "/repo")
        self.assertIsNone(args.output)
        self.assertEqual(args.exclude, [])
        self.assertFalse(args.skip_tests)
        self.assertFalse(args.compact)

    def test_crawl_exclude_is_repeatable(self):
        args = self.parser.parse_args(["crawl", "/repo", "--exclude", "vendor", "--exclude", "out"])
        self.assertEqual(args.exclude, ["vendor", "out"])

    def test_generate_emit_only_is_repeatable_and_defaults_empty(self):
        args = self.parser.parse_args(["generate-emit", "plan.json", "--repo", "/repo"])
        self.assertEqual(args.only, [])
        args = self.parser.parse_args(
            ["generate-emit", "plan.json", "--repo", "/repo", "--only", "a", "--only", "b"]
        )
        self.assertEqual(args.only, ["a", "b"])

    def test_generate_ingest_defaults(self):
        args = self.parser.parse_args(["generate-ingest", "plan.json", "--repo", "/repo"])
        self.assertIsNone(args.responses_dir)
        self.assertIsNone(args.output_dir)
        self.assertFalse(args.force)
        self.assertFalse(args.no_validate)

    def test_update_emit_defaults_match_documentation(self):
        args = self.parser.parse_args(["update-emit"])
        self.assertEqual(args.repo, ".")
        self.assertEqual(args.base, "HEAD~1")
        self.assertEqual(args.head, "HEAD")
        self.assertIsNone(args.feature)
        self.assertIsNone(args.prompts_dir)

    def test_update_ingest_defaults(self):
        args = self.parser.parse_args(["update-ingest"])
        self.assertEqual(args.repo, ".")
        self.assertIsNone(args.responses_dir)
        self.assertIsNone(args.feature)
        self.assertFalse(args.commit)
        self.assertFalse(args.no_validate)

    def test_doctor_json_flag_defaults_false(self):
        args = self.parser.parse_args(["doctor", "/repo"])
        self.assertFalse(args.json)
        args = self.parser.parse_args(["doctor", "/repo", "--json"])
        self.assertTrue(args.json)

    def test_validate_accepts_multiple_paths(self):
        args = self.parser.parse_args(["validate", "a/SKILL.md", "b/SKILL.md"])
        self.assertEqual(args.paths, ["a/SKILL.md", "b/SKILL.md"])


# ---------------------------------------------------------------------------
# main() dispatches to the wired handler and returns its result
# ---------------------------------------------------------------------------

class TestMainDispatch(unittest.TestCase):
    def test_main_calls_wired_handler_and_returns_its_exit_code(self):
        calls = []

        def fake_doctor(args):
            calls.append(args.path)
            return 7

        original = cli._cmd_doctor
        cli._cmd_doctor = fake_doctor
        try:
            rc = cli.main(["doctor", "/some/repo"])
        finally:
            cli._cmd_doctor = original

        self.assertEqual(rc, 7)
        self.assertEqual(calls, ["/some/repo"])


if __name__ == "__main__":
    unittest.main()
