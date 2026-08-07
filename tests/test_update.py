"""
Smoke tests for tools.skill_generator.update — the Phase-2 incremental updater.

Coverage:
  - _bump_version: parse existing version integer; default when missing; never
    returns zero; always returns (old, old+1)
  - _domain_from_skill: extract CamelCase.java names, XML, SQL, shell file
    references from an existing SKILL.md; unknown/empty text yields empty lists
  - _map_files_to_features: match changed basenames to the feature whose
    SKILL.md references them; unmatched files do not appear in the result; empty
    skills_dir returns {}
  - _resolve_skills_dir: prefers .github/skills over skills/; returns None when
    neither exists; handles both present (first candidate wins)
  - ingest_responses (no git commit): happy-path version bump + date rewrite;
    validation gate blocks a malformed response; empty response file is skipped;
    missing response file is reported in failed[]

All tests use stdlib only (tempfile, pathlib, re, datetime, unittest).
"""
from __future__ import annotations

import re
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools.skill_generator.update import (
    _bump_version,
    _domain_from_skill,
    _map_files_to_features,
    _resolve_skills_dir,
    ingest_responses,
)


# ---------------------------------------------------------------------------
# Minimal valid SKILL.md that satisfies the artifact-3 validator.
# Used wherever ingest_responses needs a real SKILL.md on disk.
# ---------------------------------------------------------------------------

_VALID_SKILL = """\
---
skill: File Delivery
domain: file-delivery
version: 3
project_type: REST API
framework: Spring Boot
java_version: 17
legacy: false
status: active
flags: none
related_skills: none
generated_by: skill_generator.agent
last_updated: 2025-01-01
---

# File Delivery

## Purpose
Handles file transfer between the portal and downstream systems.

## Entry Points
- REST: POST /api/files → FileDeliveryController.create()

## Business Logic

### Core Flow
1. Receive upload — FileDeliveryController.create()
2. Persist record — FileDeliveryService.save()

### Validation Rules
- File must be non-null — FileDeliveryService.validate()

### Business Rules
- Status transitions follow the defined state machine — FileDeliveryService.transition()

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| FileDeliveryController.java | Controller | REST endpoint |
| FileDeliveryService.java | Service | Business logic |

## Data Flow
```
POST /api/files
   |
   v
FileDeliveryController.create()
   |
   v
FileDeliveryService.save()
```

## Database & Storage
- Table: file_delivery

## External Dependencies
none found

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| IllegalArgumentException | null input | 400 Bad Request |

## Edge Cases
- Null file rejected — FileDeliveryService.validate()

## Legacy Notes
none found

## Related Skills
none found

## AI Agent Instructions
1. Always check FileDeliveryService.validate() before adding new validation rules.
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# _bump_version
# ---------------------------------------------------------------------------

class TestBumpVersion(unittest.TestCase):
    def test_standard_version_bumped(self):
        md = "---\nversion: 5\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 5)
        self.assertEqual(new, 6)

    def test_version_one_becomes_two(self):
        old, new = _bump_version("version: 1\n")
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_missing_version_defaults_to_one(self):
        old, new = _bump_version("no version field here")
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_new_always_greater_than_old(self):
        for v in range(1, 20):
            old, new = _bump_version(f"version: {v}\n")
            self.assertGreater(new, old)

    def test_large_version_number(self):
        old, new = _bump_version("version: 999\n")
        self.assertEqual(old, 999)
        self.assertEqual(new, 1000)

    def test_version_field_mid_document(self):
        md = "skill: X\ndomain: x\nversion: 7\nstatus: active\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 7)
        self.assertEqual(new, 8)

    def test_does_not_match_version_in_body_text(self):
        # The regex uses re.MULTILINE and anchors to start-of-line, so a
        # mid-sentence occurrence like "introduced in version: 4" should not
        # match if it doesn't start the line.
        md = "---\nversion: 2\n---\nThis was introduced in version: 4\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 2)
        self.assertEqual(new, 3)


# ---------------------------------------------------------------------------
# _domain_from_skill
# ---------------------------------------------------------------------------

class TestDomainFromSkill(unittest.TestCase):
    def test_feature_id_becomes_id_and_name(self):
        d = _domain_from_skill("no classes here", "my-feature")
        self.assertEqual(d["id"], "my-feature")
        self.assertEqual(d["name"], "my-feature")

    def test_camelcase_java_refs_extracted_as_classes(self):
        text = "| FileDeliveryController.java | Controller | REST |"
        d = _domain_from_skill(text, "fd")
        self.assertIn("FileDeliveryController", d["classes"])

    def test_multiple_java_refs_extracted(self):
        text = (
            "FileDeliveryService.java handles business logic.\n"
            "FileDeliveryController.java is the REST layer.\n"
            "FileDeliveryRepository.java talks to the DB.\n"
        )
        d = _domain_from_skill(text, "fd")
        for cls in ("FileDeliveryService", "FileDeliveryController", "FileDeliveryRepository"):
            self.assertIn(cls, d["classes"])

    def test_duplicate_java_refs_deduplicated(self):
        text = "FileDeliveryService.java and again FileDeliveryService.java"
        d = _domain_from_skill(text, "fd")
        self.assertEqual(d["classes"].count("FileDeliveryService"), 1)

    def test_lowercase_java_file_not_extracted(self):
        # Pattern requires leading uppercase letter (CamelCase guard).
        text = "utilities.java and helpers.java"
        d = _domain_from_skill(text, "x")
        self.assertEqual(d["classes"], [])

    def test_xml_files_extracted(self):
        text = "struts-config.xml and applicationContext.xml are wired here."
        d = _domain_from_skill(text, "fd")
        self.assertIn("struts-config.xml", d["xmlSources"][0])
        self.assertIn("applicationContext.xml", d["xmlSources"][1])

    def test_sql_files_extracted(self):
        text = "Procedure lives in file_delivery.sql"
        d = _domain_from_skill(text, "fd")
        self.assertTrue(any("file_delivery.sql" in s for s in d["sqlSources"]))

    def test_shell_files_extracted(self):
        text = "Orchestrated by deploy.sh"
        d = _domain_from_skill(text, "fd")
        self.assertTrue(any("deploy.sh" in s for s in d["shellSources"]))

    def test_empty_text_returns_empty_lists(self):
        d = _domain_from_skill("", "empty")
        self.assertEqual(d["classes"], [])
        self.assertEqual(d["xmlSources"], [])
        self.assertEqual(d["sqlSources"], [])
        self.assertEqual(d["shellSources"], [])

    def test_description_always_empty_string(self):
        d = _domain_from_skill("some text", "x")
        self.assertEqual(d["description"], "")


# ---------------------------------------------------------------------------
# _map_files_to_features
# ---------------------------------------------------------------------------

class TestMapFilesToFeatures(unittest.TestCase):
    def _setup_skills_dir(self, tmpdir: str, feature_id: str, skill_text: str) -> Path:
        skills_dir = Path(tmpdir) / "skills"
        skill_path = skills_dir / feature_id / "SKILL.md"
        _write(skill_path, skill_text)
        return skills_dir

    def test_matched_file_appears_in_result(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup_skills_dir(
                td, "file-delivery",
                "| FileDeliveryService.java | Service | logic |"
            )
            result = _map_files_to_features(
                ["src/main/java/FileDeliveryService.java"], skills_dir
            )
            self.assertIn("file-delivery", result)
            self.assertIn("src/main/java/FileDeliveryService.java",
                          result["file-delivery"])

    def test_unmatched_file_absent_from_result(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup_skills_dir(
                td, "file-delivery",
                "| FileDeliveryService.java | Service | logic |"
            )
            result = _map_files_to_features(["UnknownClass.java"], skills_dir)
            self.assertNotIn("file-delivery", result)

    def test_file_matched_to_correct_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            _write(
                skills_dir / "feature-a" / "SKILL.md",
                "| AlphaService.java | Service | A |"
            )
            _write(
                skills_dir / "feature-b" / "SKILL.md",
                "| BetaService.java | Service | B |"
            )
            result = _map_files_to_features(["BetaService.java"], skills_dir)
            self.assertIn("feature-b", result)
            self.assertNotIn("feature-a", result)

    def test_empty_changed_list_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup_skills_dir(
                td, "fd", "| FileDeliveryService.java | Service | |"
            )
            result = _map_files_to_features([], skills_dir)
            self.assertEqual(result, {})

    def test_nonexistent_skills_dir_returns_empty(self):
        result = _map_files_to_features(
            ["anything.java"], Path("/nonexistent/path/skills")
        )
        self.assertEqual(result, {})

    def test_file_matched_to_multiple_features(self):
        # SharedUtil.java referenced by two features — appears in both.
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            _write(skills_dir / "feat-a" / "SKILL.md", "SharedUtil.java used here")
            _write(skills_dir / "feat-b" / "SKILL.md", "SharedUtil.java also used")
            result = _map_files_to_features(["SharedUtil.java"], skills_dir)
            self.assertIn("feat-a", result)
            self.assertIn("feat-b", result)


# ---------------------------------------------------------------------------
# _resolve_skills_dir
# ---------------------------------------------------------------------------

class TestResolveSkillsDir(unittest.TestCase):
    def test_github_skills_preferred(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            gh = repo / ".github" / "skills"
            gh.mkdir(parents=True)
            plain = repo / "skills"
            plain.mkdir()
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, gh)

    def test_plain_skills_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            plain = repo / "skills"
            plain.mkdir()
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, plain)

    def test_neither_present_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            result = _resolve_skills_dir(Path(td))
            self.assertIsNone(result)

    def test_only_github_skills_present(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            gh = repo / ".github" / "skills"
            gh.mkdir(parents=True)
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, gh)


# ---------------------------------------------------------------------------
# ingest_responses (no git commit)
# ---------------------------------------------------------------------------

class TestIngestResponsesHappyPath(unittest.TestCase):
    def _setup(self, tmpdir: str):
        repo = Path(tmpdir)
        skills_dir = repo / ".github" / "skills"
        feature_id = "file-delivery"
        skill_path = skills_dir / feature_id / "SKILL.md"
        _write(skill_path, _VALID_SKILL)

        responses_dir = repo / ".skill-gen" / ".update-responses"
        responses_dir.mkdir(parents=True, exist_ok=True)
        return repo, skills_dir, skill_path, responses_dir, feature_id

    def test_version_bumped_on_ingest(self):
        with tempfile.TemporaryDirectory() as td:
            repo, skills_dir, skill_path, responses_dir, fid = self._setup(td)
            # Write a response that is a copy of the valid skill (will validate)
            _write(responses_dir / f"{fid}.md", _VALID_SKILL)

            result = ingest_responses(repo, responses_dir=responses_dir, commit=False)

            self.assertEqual(len(result["failed"]), 0, result["failed"])
            self.assertEqual(len(result["updated"]), 1)
            updated_text = skill_path.read_text(encoding="utf-8")
            # Old version was 3; must now be 4
            self.assertIn("version: 4", updated_text)

    def test_last_updated_set_to_today(self):
        with tempfile.TemporaryDirectory() as td:
            repo, skills_dir, skill_path, responses_dir, fid = self._setup(td)
            _write(responses_dir / f"{fid}.md", _VALID_SKILL)

            ingest_responses(repo, responses_dir=responses_dir, commit=False)

            updated_text = skill_path.read_text(encoding="utf-8")
            today = date.today().isoformat()
            self.assertIn(f"last_updated: {today}", updated_text)

    def test_stale_date_in_response_is_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            repo, skills_dir, skill_path, responses_dir, fid = self._setup(td)
            stale_response = _VALID_SKILL.replace(
                "last_updated: 2025-01-01", "last_updated: 2020-06-15"
            )
            _write(responses_dir / f"{fid}.md", stale_response)

            ingest_responses(repo, responses_dir=responses_dir, commit=False)

            updated_text = skill_path.read_text(encoding="utf-8")
            self.assertNotIn("2020-06-15", updated_text)
            self.assertIn(date.today().isoformat(), updated_text)


class TestIngestResponsesValidationGate(unittest.TestCase):
    def test_malformed_response_not_written(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            skills_dir = repo / ".github" / "skills"
            fid = "file-delivery"
            skill_path = skills_dir / fid / "SKILL.md"
            _write(skill_path, _VALID_SKILL)

            responses_dir = repo / ".skill-gen" / ".update-responses"
            responses_dir.mkdir(parents=True, exist_ok=True)
            # A response with no frontmatter fails validation
            _write(responses_dir / f"{fid}.md", "# Just some text, no YAML frontmatter\n")

            result = ingest_responses(repo, responses_dir=responses_dir, commit=False)

            self.assertEqual(len(result["updated"]), 0)
            self.assertEqual(len(result["failed"]), 1)
            self.assertEqual(result["failed"][0]["feature"], fid)
            # Original skill must be untouched
            self.assertEqual(skill_path.read_text(encoding="utf-8"), _VALID_SKILL)

    def test_validation_skipped_when_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            skills_dir = repo / ".github" / "skills"
            fid = "file-delivery"
            skill_path = skills_dir / fid / "SKILL.md"
            _write(skill_path, _VALID_SKILL)

            responses_dir = repo / ".skill-gen" / ".update-responses"
            responses_dir.mkdir(parents=True, exist_ok=True)
            bad_response = "# No frontmatter at all\nsome content here.\n"
            _write(responses_dir / f"{fid}.md", bad_response)

            result = ingest_responses(
                repo, responses_dir=responses_dir, commit=False,
                validate_schema=False
            )

            # With validation off, the bad content is written
            self.assertEqual(len(result["updated"]), 1)


class TestIngestResponsesEdgeCases(unittest.TestCase):
    def test_empty_response_file_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            skills_dir = repo / ".github" / "skills"
            fid = "file-delivery"
            _write(skills_dir / fid / "SKILL.md", _VALID_SKILL)

            responses_dir = repo / ".skill-gen" / ".update-responses"
            responses_dir.mkdir(parents=True, exist_ok=True)
            _write(responses_dir / f"{fid}.md", "   \n  \n")  # only whitespace

            result = ingest_responses(repo, responses_dir=responses_dir, commit=False)

            self.assertEqual(len(result["updated"]), 0)
            self.assertTrue(
                any(f["feature"] == fid for f in result["failed"]),
                "empty response must appear in failed[]"
            )

    def test_missing_response_file_reported_in_failed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            skills_dir = repo / ".github" / "skills"
            fid = "file-delivery"
            _write(skills_dir / fid / "SKILL.md", _VALID_SKILL)

            responses_dir = repo / ".skill-gen" / ".update-responses"
            responses_dir.mkdir(parents=True, exist_ok=True)
            # No response file written

            result = ingest_responses(
                repo, responses_dir=responses_dir, commit=False,
                feature=fid  # target specific feature so it looks for the missing file
            )

            self.assertEqual(len(result["updated"]), 0)
            self.assertTrue(
                any(f["feature"] == fid for f in result["failed"]),
                "missing response must appear in failed[]"
            )

    def test_no_skills_dir_returns_early(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            # No .github/skills or skills/ present
            result = ingest_responses(repo, commit=False)
            self.assertIn("reason", result)
            self.assertIn("no skills directory", result["reason"])

    def test_fenced_response_is_unwrapped(self):
        """ingest_responses calls _strip_markdown_fence before writing.
        A response wrapped in ```markdown...``` must still be written cleanly."""
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            skills_dir = repo / ".github" / "skills"
            fid = "file-delivery"
            skill_path = skills_dir / fid / "SKILL.md"
            _write(skill_path, _VALID_SKILL)

            responses_dir = repo / ".skill-gen" / ".update-responses"
            responses_dir.mkdir(parents=True, exist_ok=True)
            # Wrap in a markdown fence as a host agent sometimes does
            fenced = f"```markdown\n{_VALID_SKILL}\n```"
            _write(responses_dir / f"{fid}.md", fenced)

            result = ingest_responses(repo, responses_dir=responses_dir, commit=False)

            self.assertEqual(len(result["failed"]), 0, result["failed"])
            self.assertEqual(len(result["updated"]), 1)
            updated_text = skill_path.read_text(encoding="utf-8")
            self.assertNotIn("```markdown", updated_text)
            self.assertIn("skill: File Delivery", updated_text)


if __name__ == "__main__":
    unittest.main()
