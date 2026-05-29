"""
Smoke tests for tools.skill_generator.update.

Covers pure-function helpers:
  - _bump_version: version parsing from frontmatter; fallback when field absent
  - _domain_from_skill: Java class / XML / SQL / shell name extraction
  - _resolve_skills_dir: preference of .github/skills/ over skills/; None when absent
  - _map_files_to_features: basename-to-feature mapping; unmatched-file handling;
      multi-feature match for a shared file
  - _git_changed_files: subprocess success, CalledProcessError fallback, and
      empty-diff fallback — all via unittest.mock to stay hermetic

Integration (ingest_responses with validate_schema=False):
  - version bumped to existing+1 and last_updated rewritten to today
  - missing response file lands in failed[]
  - missing existing SKILL.md lands in failed[]
  - empty/whitespace response lands in failed[]
  - markdown fences stripped before writing
  - no-skills-dir repo returns a top-level "reason" key

All tests use stdlib only (tempfile, pathlib, datetime, unittest, unittest.mock).
"""
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.skill_generator.update import (
    _bump_version,
    _domain_from_skill,
    _git_changed_files,
    _map_files_to_features,
    _resolve_skills_dir,
    ingest_responses,
)


# ---------------------------------------------------------------------------
# _bump_version
# ---------------------------------------------------------------------------

class TestBumpVersion(unittest.TestCase):

    def test_version_present_bumped_by_one(self):
        old, new = _bump_version("---\nversion: 3\n---\n")
        self.assertEqual(old, 3)
        self.assertEqual(new, 4)

    def test_version_1_becomes_2(self):
        old, new = _bump_version("---\nversion: 1\n---\n")
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_no_version_field_defaults_old_to_1(self):
        old, new = _bump_version("---\nskill: foo\n---\n")
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_version_zero_bumped_to_one(self):
        old, new = _bump_version("---\nversion: 0\n---\n")
        self.assertEqual(old, 0)
        self.assertEqual(new, 1)

    def test_first_occurrence_wins_over_later_body_mention(self):
        # re.search returns the first MULTILINE match, so frontmatter wins.
        md = "---\nversion: 5\n---\nSome text about version: 99\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 5)
        self.assertEqual(new, 6)


# ---------------------------------------------------------------------------
# _domain_from_skill
# ---------------------------------------------------------------------------

class TestDomainFromSkill(unittest.TestCase):

    def test_feature_id_used_as_id_and_name(self):
        d = _domain_from_skill("", "my-feature")
        self.assertEqual(d["id"], "my-feature")
        self.assertEqual(d["name"], "my-feature")

    def test_description_is_always_empty_string(self):
        d = _domain_from_skill("", "x")
        self.assertEqual(d["description"], "")

    def test_java_classes_extracted(self):
        md = (
            "FileDeliveryService.java is the main class.\n"
            "FileDeliveryController.java handles HTTP.\n"
        )
        d = _domain_from_skill(md, "fd")
        self.assertIn("FileDeliveryService", d["classes"])
        self.assertIn("FileDeliveryController", d["classes"])

    def test_xml_sources_extracted_with_suffix_marker(self):
        md = "Action mappings in struts-config.xml are authoritative.\n"
        d = _domain_from_skill(md, "fd")
        self.assertTrue(any("struts-config.xml" in s for s in d["xmlSources"]))

    def test_sql_sources_extracted(self):
        md = "Schema lives in schema.sql\n"
        d = _domain_from_skill(md, "fd")
        self.assertTrue(any("schema.sql" in s for s in d["sqlSources"]))

    def test_shell_sources_extracted(self):
        md = "Batch orchestration via run.sh\n"
        d = _domain_from_skill(md, "fd")
        self.assertTrue(any("run.sh" in s for s in d["shellSources"]))

    def test_empty_text_yields_empty_classes(self):
        d = _domain_from_skill("no java here", "empty")
        self.assertEqual(d["classes"], [])

    def test_no_duplicate_classes(self):
        # The same class name mentioned twice should not be counted twice.
        md = "FooService.java is the service.\nFooService.java has a bug.\n"
        d = _domain_from_skill(md, "foo")
        self.assertEqual(d["classes"].count("FooService"), 1)


# ---------------------------------------------------------------------------
# _resolve_skills_dir
# ---------------------------------------------------------------------------

class TestResolveSkillsDir(unittest.TestCase):

    def test_github_skills_preferred_over_skills(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".github" / "skills").mkdir(parents=True)
            (root / "skills").mkdir()
            self.assertEqual(_resolve_skills_dir(root), root / ".github" / "skills")

    def test_skills_used_when_github_skills_absent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "skills").mkdir()
            self.assertEqual(_resolve_skills_dir(root), root / "skills")

    def test_returns_none_when_neither_exists(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(_resolve_skills_dir(Path(td)))


# ---------------------------------------------------------------------------
# _map_files_to_features
# ---------------------------------------------------------------------------

class TestMapFilesToFeatures(unittest.TestCase):

    def _write_skill(self, skills_dir: Path, feature_id: str, text: str) -> None:
        skill_dir = skills_dir / feature_id
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")

    def test_returns_empty_dict_when_skills_dir_missing(self):
        result = _map_files_to_features(["Foo.java"], Path("/nonexistent/path"))
        self.assertEqual(result, {})

    def test_file_mapped_to_feature_by_basename(self):
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td)
            self._write_skill(skills, "file-delivery",
                              "FileDeliveryService.java is the entry point.\n")
            result = _map_files_to_features(
                ["src/main/java/FileDeliveryService.java"], skills
            )
            self.assertIn("file-delivery", result)
            self.assertIn("src/main/java/FileDeliveryService.java",
                          result["file-delivery"])

    def test_unmatched_file_absent_from_result(self):
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td)
            self._write_skill(skills, "file-delivery",
                              "FileDeliveryService.java mentioned here.\n")
            result = _map_files_to_features(["UnknownClass.java"], skills)
            self.assertEqual(result, {})

    def test_shared_file_matches_multiple_features(self):
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td)
            self._write_skill(skills, "feature-a",
                              "SharedUtil.java is used here.\n")
            self._write_skill(skills, "feature-b",
                              "SharedUtil.java is also used here.\n")
            result = _map_files_to_features(
                ["com/example/SharedUtil.java"], skills
            )
            self.assertIn("feature-a", result)
            self.assertIn("feature-b", result)

    def test_empty_changed_files_gives_empty_result(self):
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td)
            self._write_skill(skills, "feature-a", "SomeClass.java\n")
            self.assertEqual(_map_files_to_features([], skills), {})

    def test_xml_file_matched_by_basename(self):
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td)
            self._write_skill(skills, "struts-app",
                              "Routing in struts-config.xml\n")
            result = _map_files_to_features(
                ["WEB-INF/struts-config.xml"], skills
            )
            self.assertIn("struts-app", result)


# ---------------------------------------------------------------------------
# ingest_responses — integration (validate_schema=False to isolate update logic)
# ---------------------------------------------------------------------------

# Minimal SKILL.md content — used for both the "existing" skill on disk and the
# simulated AI response.  Version is 2; ingest must force-bump it to 3.
_SKILL_V2 = """\
---
skill: test-feature
domain: test
version: 2
project_type: REST API
framework: Spring Boot
java_version: 17
legacy: false
status: active
flags: []
related_skills: []
generated_by: test
last_updated: 2025-01-01
---

## Purpose
Handles test cases.

## Entry Points
none found

## Business Logic

### Core Flow
none found

### Validation Rules
none found

### Business Rules
none found

## Key Classes & Files
none found

## Data Flow
none found

## Database & Storage
none found

## External Dependencies
none found

## Error Handling
none found

## Edge Cases
none found

## Legacy Notes
none found

## Related Skills
none found

## AI Agent Instructions
none found
"""


class TestIngestResponses(unittest.TestCase):

    def _setup(self, td: str, feature_id: str = "test-feature"):
        root = Path(td)
        skills_dir = root / ".github" / "skills"
        responses_dir = root / ".skill-gen" / ".update-responses"
        skill_path = skills_dir / feature_id / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        responses_dir.mkdir(parents=True, exist_ok=True)
        return root, responses_dir, skill_path

    def test_version_bumped_and_last_updated_set_to_today(self):
        with tempfile.TemporaryDirectory() as td:
            root, responses_dir, skill_path = self._setup(td)
            skill_path.write_text(_SKILL_V2, encoding="utf-8")
            (responses_dir / "test-feature.md").write_text(_SKILL_V2, encoding="utf-8")

            result = ingest_responses(root, responses_dir=str(responses_dir),
                                      validate_schema=False)

            self.assertIn(str(skill_path), result["updated"])
            text = skill_path.read_text(encoding="utf-8")
            self.assertIn("version: 3", text)
            self.assertIn(f"last_updated: {date.today().isoformat()}", text)

    def test_missing_response_file_goes_to_failed(self):
        with tempfile.TemporaryDirectory() as td:
            root, responses_dir, skill_path = self._setup(td)
            skill_path.write_text(_SKILL_V2, encoding="utf-8")
            # No response file written.

            result = ingest_responses(root, responses_dir=str(responses_dir),
                                      feature="test-feature",
                                      validate_schema=False)

            self.assertEqual(result["updated"], [])
            self.assertEqual(len(result["failed"]), 1)
            self.assertEqual(result["failed"][0]["reason"], "response missing")

    def test_missing_existing_skill_goes_to_failed(self):
        with tempfile.TemporaryDirectory() as td:
            root, responses_dir, skill_path = self._setup(td)
            # Write response but NOT the existing SKILL.md.
            (responses_dir / "test-feature.md").write_text(_SKILL_V2, encoding="utf-8")

            result = ingest_responses(root, responses_dir=str(responses_dir),
                                      feature="test-feature",
                                      validate_schema=False)

            self.assertEqual(result["updated"], [])
            self.assertEqual(len(result["failed"]), 1)
            self.assertEqual(result["failed"][0]["reason"], "skill not found")

    def test_empty_response_goes_to_failed(self):
        with tempfile.TemporaryDirectory() as td:
            root, responses_dir, skill_path = self._setup(td)
            skill_path.write_text(_SKILL_V2, encoding="utf-8")
            (responses_dir / "test-feature.md").write_text("   ", encoding="utf-8")

            result = ingest_responses(root, responses_dir=str(responses_dir),
                                      validate_schema=False)

            self.assertEqual(result["updated"], [])
            self.assertEqual(len(result["failed"]), 1)
            self.assertEqual(result["failed"][0]["reason"], "empty response")

    def test_markdown_fence_stripped_before_writing(self):
        with tempfile.TemporaryDirectory() as td:
            root, responses_dir, skill_path = self._setup(td)
            skill_path.write_text(_SKILL_V2, encoding="utf-8")
            fenced = "```markdown\n" + _SKILL_V2 + "\n```"
            (responses_dir / "test-feature.md").write_text(fenced, encoding="utf-8")

            result = ingest_responses(root, responses_dir=str(responses_dir),
                                      validate_schema=False)

            self.assertIn(str(skill_path), result["updated"])
            self.assertNotIn("```", skill_path.read_text(encoding="utf-8"))

    def test_no_skills_dir_returns_reason_key(self):
        with tempfile.TemporaryDirectory() as td:
            result = ingest_responses(Path(td), validate_schema=False)
            self.assertIn("reason", result)
            self.assertEqual(result["updated"], [])

    def test_multiple_features_all_updated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            responses_dir = root / ".skill-gen" / ".update-responses"
            responses_dir.mkdir(parents=True)

            for feature in ("alpha", "beta"):
                skill_path = root / ".github" / "skills" / feature / "SKILL.md"
                skill_path.parent.mkdir(parents=True, exist_ok=True)
                # Give each feature a distinct version so bumps are traceable.
                content = _SKILL_V2.replace("test-feature", feature)
                skill_path.write_text(content, encoding="utf-8")
                (responses_dir / f"{feature}.md").write_text(content, encoding="utf-8")

            result = ingest_responses(root, responses_dir=str(responses_dir),
                                      validate_schema=False)

            self.assertEqual(len(result["updated"]), 2)
            self.assertEqual(result["failed"], [])


class TestIngestResponsesForceCorrections(unittest.TestCase):
    """Regression tests for the two force-overwrite paths in ingest_responses:
    the AI is allowed to return a wrong version number or a stale date, and
    ingest must silently correct both."""

    def _setup(self, td: str, feature_id: str = "test-feature"):
        root = Path(td)
        skills_dir = root / ".github" / "skills"
        responses_dir = root / ".skill-gen" / ".update-responses"
        skill_path = skills_dir / feature_id / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        responses_dir.mkdir(parents=True, exist_ok=True)
        return root, responses_dir, skill_path

    def test_ai_wrong_version_corrected_to_existing_plus_one(self):
        """If the AI response says version: 99 but the existing skill is version: 3,
        ingest must write version: 4, not version: 100 or version: 99."""
        with tempfile.TemporaryDirectory() as td:
            root, responses_dir, skill_path = self._setup(td)
            existing = _SKILL_V2.replace("version: 2", "version: 3")
            response = _SKILL_V2.replace("version: 2", "version: 99")
            skill_path.write_text(existing, encoding="utf-8")
            (responses_dir / "test-feature.md").write_text(response, encoding="utf-8")

            ingest_responses(root, responses_dir=str(responses_dir),
                             validate_schema=False)

            written = skill_path.read_text(encoding="utf-8")
            self.assertIn("version: 4", written)
            self.assertNotIn("version: 99", written)

    def test_stale_date_in_response_replaced_with_today(self):
        """A response with a stale last_updated must be rewritten to today
        regardless of the date the AI returned."""
        stale_response = _SKILL_V2.replace("last_updated: 2025-01-01",
                                           "last_updated: 2020-06-15")
        with tempfile.TemporaryDirectory() as td:
            root, responses_dir, skill_path = self._setup(td)
            skill_path.write_text(_SKILL_V2, encoding="utf-8")
            (responses_dir / "test-feature.md").write_text(stale_response,
                                                           encoding="utf-8")

            ingest_responses(root, responses_dir=str(responses_dir),
                             validate_schema=False)

            written = skill_path.read_text(encoding="utf-8")
            self.assertNotIn("last_updated: 2020-06-15", written)
            self.assertIn(f"last_updated: {date.today().isoformat()}", written)


class TestIngestResponsesFeatureFilter(unittest.TestCase):
    """The `feature=` kwarg must restrict processing to exactly one feature."""

    def _setup_two_features(self, td: str):
        root = Path(td)
        responses_dir = root / ".skill-gen" / ".update-responses"
        responses_dir.mkdir(parents=True)
        for fid in ("alpha", "beta"):
            skill_path = root / ".github" / "skills" / fid / "SKILL.md"
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            content = _SKILL_V2.replace("test-feature", fid)
            skill_path.write_text(content, encoding="utf-8")
            (responses_dir / f"{fid}.md").write_text(content, encoding="utf-8")
        return root, responses_dir

    def test_feature_filter_updates_only_named_feature(self):
        with tempfile.TemporaryDirectory() as td:
            root, responses_dir = self._setup_two_features(td)
            result = ingest_responses(root, responses_dir=str(responses_dir),
                                      feature="alpha", validate_schema=False)

            updated = [Path(p).parent.name for p in result["updated"]]
            self.assertIn("alpha", updated)
            self.assertNotIn("beta", updated)

    def test_no_feature_filter_updates_all(self):
        with tempfile.TemporaryDirectory() as td:
            root, responses_dir = self._setup_two_features(td)
            result = ingest_responses(root, responses_dir=str(responses_dir),
                                      validate_schema=False)

            updated = [Path(p).parent.name for p in result["updated"]]
            self.assertIn("alpha", updated)
            self.assertIn("beta", updated)


# ---------------------------------------------------------------------------
# _git_changed_files
# ---------------------------------------------------------------------------

class TestGitChangedFiles(unittest.TestCase):
    """These tests mock subprocess.run so no real git repo is needed.
    The function lives in tools.skill_generator.update, so we patch the
    subprocess reference *there*, not in the stdlib module."""

    _TARGET = "tools.skill_generator.update.subprocess.run"

    def test_diff_success_returns_file_list(self):
        ok = MagicMock()
        ok.stdout = "src/Foo.java\nsrc/Bar.java\n"
        with patch(self._TARGET, return_value=ok):
            files = _git_changed_files(Path("/repo"), "HEAD~1", "HEAD")
        self.assertIn("src/Foo.java", files)
        self.assertIn("src/Bar.java", files)
        self.assertEqual(len(files), 2)

    def test_diff_strips_blank_lines(self):
        ok = MagicMock()
        ok.stdout = "src/Foo.java\n\n  \nsrc/Bar.java\n"
        with patch(self._TARGET, return_value=ok):
            files = _git_changed_files(Path("/repo"), "HEAD~1", "HEAD")
        self.assertEqual(files, ["src/Foo.java", "src/Bar.java"])

    def test_diff_failure_falls_back_to_status(self):
        status = MagicMock()
        status.stdout = " M src/Foo.java\n?? src/New.java\n"
        with patch(self._TARGET,
                   side_effect=[subprocess.CalledProcessError(1, "git diff"), status]):
            files = _git_changed_files(Path("/repo"), "HEAD~1", "HEAD")
        self.assertTrue(any("Foo.java" in f for f in files))
        self.assertTrue(any("New.java" in f for f in files))

    def test_empty_diff_falls_back_to_status(self):
        """An empty diff output (e.g. shallow clone with only one commit) must
        trigger the git status fallback rather than returning an empty list."""
        empty = MagicMock()
        empty.stdout = ""
        status = MagicMock()
        status.stdout = " M changed.java\n"
        with patch(self._TARGET, side_effect=[empty, status]):
            files = _git_changed_files(Path("/repo"), "HEAD~1", "HEAD")
        self.assertTrue(any("changed.java" in f for f in files))

    def test_status_porcelain_format_parsed_correctly(self):
        """git status --porcelain prefixes each path with a 2-char XY status
        plus a space (3 chars total). Slicing from index 3 must give the path."""
        status = MagicMock()
        # XY status followed by space then path — 3 prefix chars
        status.stdout = "?? new_feature/FooService.java\n M src/Bar.java\n"
        with patch(self._TARGET,
                   side_effect=[subprocess.CalledProcessError(128, "git diff"), status]):
            files = _git_changed_files(Path("/repo"), "HEAD~1", "HEAD")
        self.assertIn("new_feature/FooService.java", files)
        self.assertIn("src/Bar.java", files)


if __name__ == "__main__":
    unittest.main()
