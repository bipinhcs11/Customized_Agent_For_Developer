"""
Smoke tests for tools.skill_generator.update — the Phase 2 incremental updater.

Covers:
  - _bump_version (missing version defaults to 1, present version increments)
  - _domain_from_skill (regex extraction of classes/xml/sql/sh references)
  - _resolve_skills_dir (.github/skills preferred over skills/, None when absent)
  - _map_files_to_features (basename match against existing skills, unmatched
    files are reported but do not raise)
  - emit_prompts: no skills dir -> empty result; manual --feature trigger with
    no source on disk -> reported as failed, not a crash
  - ingest_responses: version bump + last_updated stamped on write; a response
    that fails schema validation is rejected and the on-disk SKILL.md is left
    untouched
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.skill_generator.update import (
    _bump_version,
    _domain_from_skill,
    _resolve_skills_dir,
    _map_files_to_features,
    emit_prompts,
    ingest_responses,
)


VALID_SKILL_MD = """---
skill: Sample Feature
domain: sample
version: 1
project_type: REST API
framework: Spring Boot
java_version: 17
legacy: false
status: active
flags: none
related_skills: none
generated_by: skill_generator.agent
last_updated: 2026-05-16
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


class TestBumpVersion(unittest.TestCase):
    def test_existing_version_increments(self):
        old, new = _bump_version(VALID_SKILL_MD)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_missing_version_defaults_to_one(self):
        old, new = _bump_version("no frontmatter here")
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)


class TestDomainFromSkill(unittest.TestCase):
    def test_extracts_classes_and_sources(self):
        skill_md = (
            "Cites SampleController.java and SampleService.java.\n"
            "Wired in applicationContext.xml, backed by sample_table.sql, "
            "run via deploy.sh."
        )
        domain = _domain_from_skill(skill_md, "sample")
        self.assertEqual(domain["id"], "sample")
        self.assertIn("SampleController", domain["classes"])
        self.assertIn("SampleService", domain["classes"])
        self.assertTrue(any("applicationContext.xml" in x for x in domain["xmlSources"]))
        self.assertTrue(any("sample_table.sql" in s for s in domain["sqlSources"]))
        self.assertTrue(any("deploy.sh" in s for s in domain["shellSources"]))

    def test_no_references_yields_empty_lists(self):
        domain = _domain_from_skill("nothing to see here", "empty")
        self.assertEqual(domain["classes"], [])
        self.assertEqual(domain["xmlSources"], [])
        self.assertEqual(domain["sqlSources"], [])
        self.assertEqual(domain["shellSources"], [])


class TestResolveSkillsDir(unittest.TestCase):
    def test_prefers_github_skills_over_skills(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / ".github" / "skills").mkdir(parents=True)
            (repo / "skills").mkdir()
            self.assertEqual(
                _resolve_skills_dir(repo), repo / ".github" / "skills"
            )

    def test_falls_back_to_skills(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "skills").mkdir()
            self.assertEqual(_resolve_skills_dir(repo), repo / "skills")

    def test_none_when_neither_exists(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(_resolve_skills_dir(Path(td)))


class TestMapFilesToFeatures(unittest.TestCase):
    def test_matched_file_maps_to_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            feature_dir = skills_dir / "sample"
            feature_dir.mkdir(parents=True)
            (feature_dir / "SKILL.md").write_text(VALID_SKILL_MD, encoding="utf-8")

            mapping = _map_files_to_features(
                ["src/main/java/com/example/SampleController.java"], skills_dir
            )
            self.assertIn("sample", mapping)
            self.assertEqual(
                mapping["sample"], ["src/main/java/com/example/SampleController.java"]
            )

    def test_unmatched_file_is_skipped_not_raised(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            feature_dir = skills_dir / "sample"
            feature_dir.mkdir(parents=True)
            (feature_dir / "SKILL.md").write_text(VALID_SKILL_MD, encoding="utf-8")

            mapping = _map_files_to_features(["src/Unrelated.java"], skills_dir)
            self.assertEqual(mapping, {})

    def test_missing_skills_dir_yields_empty_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            mapping = _map_files_to_features(["a.java"], Path(td) / "no-such-dir")
            self.assertEqual(mapping, {})


class TestEmitPrompts(unittest.TestCase):
    def test_no_skills_dir_returns_empty_result(self):
        with tempfile.TemporaryDirectory() as td:
            result = emit_prompts(td)
            self.assertEqual(result, {"written": [], "skipped": [], "failed": []})

    def test_manual_feature_with_no_source_is_reported_failed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            feature_dir = repo / ".github" / "skills" / "sample"
            feature_dir.mkdir(parents=True)
            (feature_dir / "SKILL.md").write_text(VALID_SKILL_MD, encoding="utf-8")

            result = emit_prompts(repo, feature="sample")
            self.assertEqual(result["written"], [])
            self.assertEqual(len(result["failed"]), 1)
            self.assertEqual(result["failed"][0]["feature"], "sample")

    def test_unknown_feature_is_reported_failed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / ".github" / "skills").mkdir(parents=True)

            result = emit_prompts(repo, feature="does-not-exist")
            self.assertEqual(result["written"], [])
            self.assertEqual(
                result["failed"], [{"feature": "does-not-exist", "reason": "skill not found"}]
            )


class TestIngestResponses(unittest.TestCase):
    def _make_repo_with_skill(self, td):
        repo = Path(td)
        feature_dir = repo / ".github" / "skills" / "sample"
        feature_dir.mkdir(parents=True)
        (feature_dir / "SKILL.md").write_text(VALID_SKILL_MD, encoding="utf-8")
        responses_dir = repo / ".skill-gen" / ".update-responses"
        responses_dir.mkdir(parents=True)
        return repo, feature_dir, responses_dir

    def test_valid_response_bumps_version_and_date(self):
        with tempfile.TemporaryDirectory() as td:
            repo, feature_dir, responses_dir = self._make_repo_with_skill(td)
            (responses_dir / "sample.md").write_text(VALID_SKILL_MD, encoding="utf-8")

            result = ingest_responses(repo, responses_dir=responses_dir)

            self.assertEqual(len(result["updated"]), 1)
            self.assertEqual(result["failed"], [])
            updated_text = (feature_dir / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("version: 2", updated_text)
            self.assertNotIn("last_updated: 2026-05-16", updated_text)

    def test_invalid_response_is_rejected_and_skill_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            repo, feature_dir, responses_dir = self._make_repo_with_skill(td)
            broken = VALID_SKILL_MD.replace("## Purpose\n", "")
            (responses_dir / "sample.md").write_text(broken, encoding="utf-8")

            result = ingest_responses(repo, responses_dir=responses_dir)

            self.assertEqual(result["updated"], [])
            self.assertEqual(len(result["failed"]), 1)
            self.assertEqual(result["failed"][0]["reason"], "validation failed")
            untouched = (feature_dir / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(untouched, VALID_SKILL_MD)

    def test_missing_response_file_is_reported_failed(self):
        with tempfile.TemporaryDirectory() as td:
            repo, feature_dir, responses_dir = self._make_repo_with_skill(td)

            result = ingest_responses(repo, responses_dir=responses_dir, feature="sample")

            self.assertEqual(result["updated"], [])
            self.assertEqual(
                result["failed"], [{"feature": "sample", "reason": "response missing"}]
            )

    def test_no_skills_dir_returns_reason(self):
        with tempfile.TemporaryDirectory() as td:
            result = ingest_responses(td)
            self.assertEqual(result["updated"], [])
            self.assertEqual(result["reason"], "no skills directory")


if __name__ == "__main__":
    unittest.main()
