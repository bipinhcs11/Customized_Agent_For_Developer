"""
Smoke tests for tools.skill_generator.update (Phase 2 incremental updater).

Covers:
  - _bump_version — pure function: returns (existing_version, existing_version+1);
    handles missing version field, extra whitespace, and multi-line documents
  - _resolve_skills_dir — returns .github/skills or skills/ depending on which
    exists in the repo root; returns None when neither exists; prefers
    .github/skills when both exist
  - _domain_from_skill — pure function: extracts Java class names, XML, SQL, and
    shell file references from an existing SKILL.md; propagates feature_id to id
    and name fields; deduplicates class names
  - _map_files_to_features — matches changed file basenames against basenames
    claimed in each existing SKILL.md; handles no-match (new feature), missing
    skills dir, and multi-feature repos
  - ingest_responses — round-trip: bumps version, forces today's date into
    last_updated, writes the refreshed SKILL.md; correctly handles missing
    response file, empty response content, absent skills directory, and the
    validate_schema=False bypass flag

All tests use stdlib only (tempfile, pathlib, datetime, unittest).
"""
from __future__ import annotations

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
# Minimal valid SKILL.md for ingest round-trip tests
# (mirrors the VALID_SAMPLE in test_validate.py — must pass the artifact-3 check)
# ---------------------------------------------------------------------------

_VALID_SKILL_V3 = """\
---
skill: Sample Feature
domain: sample
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

# Sample Feature

## Purpose
Does something useful for the business.

## Entry Points
- REST: GET /api/sample → SampleController.get()

## Business Logic

### Core Flow
1. Receive request — SampleController.get()
2. Process — SampleService.process()

### Validation Rules
- Input must be non-null — SampleService.validate()

### Business Rules
- Returns 200 on success — SampleService.process()

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| SampleController.java | Controller | REST endpoint |

## Data Flow
```
GET /api/sample
   |
   v
SampleController.get()
```

## Database & Storage
- Tables: sample

## External Dependencies
none found

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| RuntimeException | failure | 500 |

## Edge Cases
- Null input handled — SampleService.validate()

## Legacy Notes
none found

## Related Skills
none found

## AI Agent Instructions
1. Always check input — SampleService.validate()
"""

# Same content but with version: 4 and today's date — expected result after ingest
_VALID_SKILL_V4_RESPONSE = _VALID_SKILL_V3.replace(
    "version: 3", "version: 4"
).replace(
    "last_updated: 2025-01-01", f"last_updated: {date.today().isoformat()}"
)


# ---------------------------------------------------------------------------
# _bump_version
# ---------------------------------------------------------------------------

class TestBumpVersion(unittest.TestCase):
    def test_standard_version_returns_old_and_incremented(self):
        md = "---\nversion: 5\nother: val\n---\nbody\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 5)
        self.assertEqual(new, 6)

    def test_version_1_increments_to_2(self):
        md = "---\nversion: 1\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_missing_version_field_defaults_to_1(self):
        md = "---\nskill: Something\n---\nbody\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_version_with_extra_whitespace(self):
        md = "---\nversion:   7\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 7)
        self.assertEqual(new, 8)

    def test_large_version_number(self):
        md = "---\nversion: 42\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 42)
        self.assertEqual(new, 43)

    def test_version_in_multiline_document(self):
        # Verify the MULTILINE flag finds it anywhere in the doc
        md = "skill: Foo\ndomain: foo\nversion: 9\nlast_updated: 2026-01-01\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 9)
        self.assertEqual(new, 10)


# ---------------------------------------------------------------------------
# _resolve_skills_dir
# ---------------------------------------------------------------------------

class TestResolveSkillsDir(unittest.TestCase):
    def test_github_skills_found(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills = root / ".github" / "skills"
            skills.mkdir(parents=True)
            result = _resolve_skills_dir(root)
            self.assertEqual(result, skills)

    def test_skills_dir_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills = root / "skills"
            skills.mkdir()
            result = _resolve_skills_dir(root)
            self.assertEqual(result, skills)

    def test_neither_exists_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            result = _resolve_skills_dir(Path(td))
            self.assertIsNone(result)

    def test_github_skills_preferred_when_both_exist(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            gh_skills = root / ".github" / "skills"
            gh_skills.mkdir(parents=True)
            (root / "skills").mkdir()
            result = _resolve_skills_dir(root)
            self.assertEqual(result, gh_skills)


# ---------------------------------------------------------------------------
# _domain_from_skill
# ---------------------------------------------------------------------------

class TestDomainFromSkill(unittest.TestCase):
    def test_feature_id_propagated_to_id_and_name(self):
        domain = _domain_from_skill("", "my-feature")
        self.assertEqual(domain["id"], "my-feature")
        self.assertEqual(domain["name"], "my-feature")

    def test_empty_skill_md_returns_empty_lists(self):
        domain = _domain_from_skill("", "x")
        self.assertEqual(domain["classes"], [])
        self.assertEqual(domain["xmlSources"], [])
        self.assertEqual(domain["sqlSources"], [])
        self.assertEqual(domain["shellSources"], [])

    def test_java_class_names_extracted(self):
        md = "| FileDeliveryService.java | Service | Handles delivery |\n"
        domain = _domain_from_skill(md, "file-delivery")
        self.assertIn("FileDeliveryService", domain["classes"])

    def test_java_class_names_deduplicated(self):
        md = "FileDeliveryService.java\nFileDeliveryService.java\n"
        domain = _domain_from_skill(md, "file-delivery")
        self.assertEqual(domain["classes"].count("FileDeliveryService"), 1)

    def test_xml_files_extracted(self):
        md = "applicationContext.xml and struts-config.xml drive wiring.\n"
        domain = _domain_from_skill(md, "x")
        xml_names = [s.split(":")[0] for s in domain["xmlSources"]]
        self.assertIn("applicationContext.xml", xml_names)
        self.assertIn("struts-config.xml", xml_names)

    def test_sql_files_extracted(self):
        md = "schema.sql contains the DDL.\n"
        domain = _domain_from_skill(md, "x")
        sql_names = [s.split(":")[0] for s in domain["sqlSources"]]
        self.assertIn("schema.sql", sql_names)

    def test_shell_files_extracted(self):
        md = "deploy.sh triggers the batch job.\n"
        domain = _domain_from_skill(md, "x")
        sh_names = [s.split(":")[0] for s in domain["shellSources"]]
        self.assertIn("deploy.sh", sh_names)

    def test_lowercase_class_names_not_extracted(self):
        # Only CamelCase names should match (first char uppercase)
        md = "| someHelper.java | Utility |\n"
        domain = _domain_from_skill(md, "x")
        self.assertEqual(domain["classes"], [])

    def test_description_is_empty_string(self):
        domain = _domain_from_skill("anything", "x")
        self.assertEqual(domain["description"], "")


# ---------------------------------------------------------------------------
# _map_files_to_features
# ---------------------------------------------------------------------------

class TestMapFilesToFeatures(unittest.TestCase):
    def _write_skill(self, skills_dir: Path, feature_id: str, content: str):
        skill_path = skills_dir / feature_id / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(content, encoding="utf-8")

    def test_missing_skills_dir_returns_empty(self):
        result = _map_files_to_features(["Foo.java"], Path("/nonexistent/path"))
        self.assertEqual(result, {})

    def test_empty_changed_files_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            skills_dir.mkdir()
            self._write_skill(skills_dir, "feat-a", "| FooService.java | Service |")
            result = _map_files_to_features([], skills_dir)
            self.assertEqual(result, {})

    def test_matching_java_file_mapped_to_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            self._write_skill(skills_dir, "feat-a", "| FooService.java | Service |")
            result = _map_files_to_features(
                ["src/main/java/FooService.java"], skills_dir
            )
            self.assertIn("feat-a", result)
            self.assertIn("src/main/java/FooService.java", result["feat-a"])

    def test_unmatched_file_not_in_result(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            self._write_skill(skills_dir, "feat-a", "| FooService.java | Service |")
            result = _map_files_to_features(["BarController.java"], skills_dir)
            self.assertNotIn("feat-a", result)
            self.assertEqual(result, {})

    def test_multiple_features_mapped_independently(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            self._write_skill(skills_dir, "feat-a", "FooService.java")
            self._write_skill(skills_dir, "feat-b", "BarService.java")
            result = _map_files_to_features(
                ["src/FooService.java", "src/BarService.java"], skills_dir
            )
            self.assertIn("feat-a", result)
            self.assertIn("feat-b", result)
            self.assertEqual(len(result["feat-a"]), 1)
            self.assertEqual(len(result["feat-b"]), 1)

    def test_xml_file_matched(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            self._write_skill(skills_dir, "feat-a", "struts-config.xml")
            result = _map_files_to_features(
                ["src/main/webapp/WEB-INF/struts-config.xml"], skills_dir
            )
            self.assertIn("feat-a", result)

    def test_sql_file_matched(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            self._write_skill(skills_dir, "feat-a", "schema.sql")
            result = _map_files_to_features(["db/schema.sql"], skills_dir)
            self.assertIn("feat-a", result)


# ---------------------------------------------------------------------------
# ingest_responses
# ---------------------------------------------------------------------------

class TestIngestResponses(unittest.TestCase):
    def _setup(self, tmpdir: str, *, version: int = 3):
        """Write a skills dir with one feature SKILL.md and return key paths."""
        root = Path(tmpdir)
        skills_dir = root / ".github" / "skills"
        feat_dir = skills_dir / "sample"
        feat_dir.mkdir(parents=True)
        skill_path = feat_dir / "SKILL.md"
        skill_content = _VALID_SKILL_V3.replace("version: 3", f"version: {version}")
        skill_path.write_text(skill_content, encoding="utf-8")
        responses_dir = root / ".skill-gen" / ".update-responses"
        responses_dir.mkdir(parents=True)
        return root, skills_dir, skill_path, responses_dir

    def test_no_skills_dir_returns_early(self):
        with tempfile.TemporaryDirectory() as td:
            result = ingest_responses(td)
            self.assertIn("reason", result)
            self.assertEqual(result["reason"], "no skills directory")
            self.assertEqual(result["updated"], [])

    def test_missing_response_file_appended_to_failed(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, _, responses_dir = self._setup(td)
            # No response file written — ingest a specific feature that has no file
            result = ingest_responses(root, feature="sample", validate_schema=False)
            self.assertEqual(result["updated"], [])
            self.assertTrue(
                any(f["feature"] == "sample" and f["reason"] == "response missing"
                    for f in result["failed"])
            )

    def test_empty_response_appended_to_failed(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, _, responses_dir = self._setup(td)
            (responses_dir / "sample.md").write_text("   \n", encoding="utf-8")
            result = ingest_responses(root, responses_dir=responses_dir,
                                      validate_schema=False)
            self.assertEqual(result["updated"], [])
            self.assertTrue(
                any(f["feature"] == "sample" and f["reason"] == "empty response"
                    for f in result["failed"])
            )

    def test_valid_response_writes_updated_skill(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, skill_path, responses_dir = self._setup(td)
            # Write a valid response (version number doesn't matter — ingest forces it)
            (responses_dir / "sample.md").write_text(
                _VALID_SKILL_V4_RESPONSE, encoding="utf-8"
            )
            result = ingest_responses(root, responses_dir=responses_dir)
            self.assertEqual(result["failed"], [])
            self.assertEqual(len(result["updated"]), 1)
            self.assertTrue(skill_path.exists())

    def test_version_bumped_in_written_skill(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, skill_path, responses_dir = self._setup(td, version=3)
            (responses_dir / "sample.md").write_text(
                _VALID_SKILL_V4_RESPONSE, encoding="utf-8"
            )
            ingest_responses(root, responses_dir=responses_dir)
            written = skill_path.read_text(encoding="utf-8")
            self.assertIn("version: 4", written)
            self.assertNotIn("version: 3", written)

    def test_last_updated_set_to_today(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, skill_path, responses_dir = self._setup(td)
            # Response has a stale date — ingest should overwrite it
            stale = _VALID_SKILL_V4_RESPONSE.replace(
                f"last_updated: {date.today().isoformat()}",
                "last_updated: 1999-12-31",
            )
            (responses_dir / "sample.md").write_text(stale, encoding="utf-8")
            ingest_responses(root, responses_dir=responses_dir)
            written = skill_path.read_text(encoding="utf-8")
            self.assertIn(f"last_updated: {date.today().isoformat()}", written)
            self.assertNotIn("last_updated: 1999-12-31", written)

    def test_invalid_response_blocked_when_schema_validation_on(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, _, responses_dir = self._setup(td)
            # Deliberately invalid: no frontmatter at all
            (responses_dir / "sample.md").write_text(
                "## Purpose\nsome content\n", encoding="utf-8"
            )
            result = ingest_responses(root, responses_dir=responses_dir,
                                      validate_schema=True)
            self.assertEqual(result["updated"], [])
            self.assertTrue(
                any(f["reason"] == "validation failed" for f in result["failed"])
            )

    def test_validate_schema_false_skips_validation_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, skill_path, responses_dir = self._setup(td)
            # Deliberately invalid SKILL.md content — should still be written
            (responses_dir / "sample.md").write_text(
                "version: 99\nlast_updated: 2099-01-01\nsome body\n",
                encoding="utf-8",
            )
            result = ingest_responses(root, responses_dir=responses_dir,
                                      validate_schema=False)
            # Validation skipped → write proceeds
            self.assertEqual(len(result["updated"]), 1)
            written = skill_path.read_text(encoding="utf-8")
            # Version forced to old+1=4 regardless of what the response says
            self.assertIn("version: 4", written)

    def test_feature_filter_restricts_to_named_feature(self):
        with tempfile.TemporaryDirectory() as td:
            root, skills_dir, _, responses_dir = self._setup(td)
            # Add a second feature skill
            other_dir = skills_dir / "other-feat"
            other_dir.mkdir()
            (other_dir / "SKILL.md").write_text(_VALID_SKILL_V3, encoding="utf-8")
            # Write responses for both, but only ingest one
            (responses_dir / "sample.md").write_text(
                _VALID_SKILL_V4_RESPONSE, encoding="utf-8"
            )
            (responses_dir / "other-feat.md").write_text(
                _VALID_SKILL_V4_RESPONSE, encoding="utf-8"
            )
            result = ingest_responses(root, responses_dir=responses_dir,
                                      feature="sample")
            updated_names = [Path(p).parent.name for p in result["updated"]]
            self.assertIn("sample", updated_names)
            self.assertNotIn("other-feat", updated_names)


if __name__ == "__main__":
    unittest.main()
