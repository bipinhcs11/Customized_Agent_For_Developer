"""
Smoke tests for tools.skill_generator.update (Phase 2 incremental updater).

Covers pure functions that require no git access or outbound calls:
  - _bump_version  — extracts and increments the frontmatter version field
  - _domain_from_skill — reconstructs a minimal domain dict from an existing SKILL.md
  - _map_files_to_features — basename-matches changed files against skill folders
  - _resolve_skills_dir — resolves .github/skills or skills directory
  - ingest_responses — version bump, date override, and disk write (commit=False)

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
# Helpers
# ---------------------------------------------------------------------------

def _make_skill(domain_id: str = "test-feature", version: int = 1) -> str:
    """Minimal but structurally complete SKILL.md for test fixtures."""
    title = domain_id.replace("-", " ").title()
    cls = domain_id.title().replace("-", "")
    return f"""\
---
skill: {title}
domain: {domain_id}
version: {version}
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

# {title}

## Purpose
Handles {domain_id}. {cls}Service.java {cls}Controller.java

## Entry Points
- REST: GET /api/{domain_id} → {cls}Controller.get()

## Business Logic

### Core Flow
1. Receive — {cls}Controller.get()
2. Process — {cls}Service.process()

### Validation Rules
- Non-null — {cls}Service.validate()

### Business Rules
- Returns 200 — {cls}Service.process()

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| {cls}Service.java | Service | core logic |

## Data Flow
```
GET /api/{domain_id}
   |
   v
{cls}Service.process()
```

## Database & Storage
- Tables: {domain_id.replace("-", "_")}

## External Dependencies
none found

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| RuntimeException | failure | 500 |

## Edge Cases
- Null handled — {cls}Service.validate()

## Legacy Notes
none found

## Related Skills
none found

## AI Agent Instructions
1. Always validate — {cls}Service.validate()
"""


# ---------------------------------------------------------------------------
# _bump_version
# ---------------------------------------------------------------------------

class TestBumpVersion(unittest.TestCase):
    def test_normal_version_bumped(self):
        md = "---\nversion: 5\ndomain: foo\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 5)
        self.assertEqual(new, 6)

    def test_version_one_bumped_to_two(self):
        md = "---\nversion: 1\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_no_space_after_colon_matched(self):
        md = "---\nversion:3\ndomain: bar\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 3)
        self.assertEqual(new, 4)

    def test_version_not_at_line_start_not_matched(self):
        # ^ in MULTILINE means line start; an indented version: should not match.
        md = "  version: 9\n"
        old, new = _bump_version(md)
        # Falls back to default of 1 → 2
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_no_version_field_defaults_to_one(self):
        md = "---\ndomain: foo\nstatus: active\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_large_version_number(self):
        md = "version: 99\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 99)
        self.assertEqual(new, 100)

    def test_first_version_field_used_when_multiple(self):
        # re.search finds the first occurrence.
        md = "version: 3\nversion: 7\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 3)
        self.assertEqual(new, 4)

    def test_new_always_equals_old_plus_one(self):
        for v in (1, 2, 10, 42):
            md = f"version: {v}\n"
            old, new = _bump_version(md)
            self.assertEqual(new, old + 1, f"version {v}: new should be old+1")


# ---------------------------------------------------------------------------
# _domain_from_skill
# ---------------------------------------------------------------------------

class TestDomainFromSkill(unittest.TestCase):
    def test_id_and_name_set_to_feature_id(self):
        d = _domain_from_skill("# nothing", "my-feature")
        self.assertEqual(d["id"], "my-feature")
        self.assertEqual(d["name"], "my-feature")

    def test_description_empty(self):
        d = _domain_from_skill("no content", "x")
        self.assertEqual(d["description"], "")

    def test_java_class_extracted(self):
        md = "Key file: FileDeliveryService.java"
        d = _domain_from_skill(md, "file-delivery")
        self.assertIn("FileDeliveryService", d["classes"])

    def test_multiple_java_classes_extracted(self):
        md = "FileDeliveryService.java and FileDeliveryController.java"
        d = _domain_from_skill(md, "file-delivery")
        self.assertIn("FileDeliveryService", d["classes"])
        self.assertIn("FileDeliveryController", d["classes"])

    def test_lowercase_class_not_extracted(self):
        # Regex requires uppercase first letter: [A-Z][A-Za-z0-9]+
        md = "helper.java is a utility"
        d = _domain_from_skill(md, "x")
        self.assertNotIn("helper", d["classes"])

    def test_java_classes_deduplicated(self):
        md = "FileDeliveryService.java and FileDeliveryService.java again"
        d = _domain_from_skill(md, "fd")
        self.assertEqual(d["classes"].count("FileDeliveryService"), 1)

    def test_xml_file_extracted(self):
        md = "Uses applicationContext.xml for bean wiring."
        d = _domain_from_skill(md, "x")
        sources = " ".join(d["xmlSources"])
        self.assertIn("applicationContext.xml", sources)

    def test_sql_file_extracted(self):
        md = "Schema defined in V1__create_table.sql"
        d = _domain_from_skill(md, "x")
        sources = " ".join(d["sqlSources"])
        self.assertIn("V1__create_table.sql", sources)

    def test_shell_file_extracted(self):
        md = "Orchestrated by deploy.sh"
        d = _domain_from_skill(md, "x")
        sources = " ".join(d["shellSources"])
        self.assertIn("deploy.sh", sources)

    def test_empty_skill_md_returns_empty_lists(self):
        d = _domain_from_skill("", "empty")
        self.assertEqual(d["classes"], [])
        self.assertEqual(d["xmlSources"], [])
        self.assertEqual(d["sqlSources"], [])
        self.assertEqual(d["shellSources"], [])

    def test_xml_sources_have_prior_skill_annotation(self):
        md = "beans.xml is used"
        d = _domain_from_skill(md, "x")
        self.assertTrue(any("from prior skill" in s for s in d["xmlSources"]))


# ---------------------------------------------------------------------------
# _map_files_to_features
# ---------------------------------------------------------------------------

def _write_skill(skills_dir: Path, feature_id: str, content: str) -> Path:
    skill_path = skills_dir / feature_id / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(content, encoding="utf-8")
    return skill_path


class TestMapFilesToFeatures(unittest.TestCase):
    def test_matching_file_mapped_to_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            _write_skill(skills_dir, "file-delivery",
                         "FileDeliveryService.java handles delivery")
            result = _map_files_to_features(
                ["src/main/java/FileDeliveryService.java"], skills_dir
            )
            self.assertIn("file-delivery", result)
            self.assertIn("src/main/java/FileDeliveryService.java",
                          result["file-delivery"])

    def test_non_matching_file_not_in_result(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            _write_skill(skills_dir, "file-delivery",
                         "FileDeliveryService.java handles delivery")
            result = _map_files_to_features(
                ["src/UnrelatedClass.java"], skills_dir
            )
            self.assertNotIn("file-delivery", result)

    def test_empty_changed_files_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            _write_skill(skills_dir, "file-delivery", "FileDeliveryService.java")
            result = _map_files_to_features([], skills_dir)
            self.assertEqual(result, {})

    def test_file_shared_by_two_features_mapped_to_both(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            _write_skill(skills_dir, "feature-a", "SharedUtils.java does A")
            _write_skill(skills_dir, "feature-b", "SharedUtils.java does B")
            result = _map_files_to_features(["src/SharedUtils.java"], skills_dir)
            self.assertIn("feature-a", result)
            self.assertIn("feature-b", result)

    def test_nonexistent_skills_dir_returns_empty(self):
        result = _map_files_to_features(
            ["src/Foo.java"], Path("/nonexistent/skills/dir/that/never/exists")
        )
        self.assertEqual(result, {})

    def test_multiple_changed_files_multiple_features(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            _write_skill(skills_dir, "invoicing", "InvoiceService.java")
            _write_skill(skills_dir, "payments", "PaymentService.java")
            result = _map_files_to_features(
                ["src/InvoiceService.java", "src/PaymentService.java"], skills_dir
            )
            self.assertIn("invoicing", result)
            self.assertIn("payments", result)

    def test_multiple_files_same_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            md = "FileDeliveryService.java and FileDeliveryController.java"
            _write_skill(skills_dir, "file-delivery", md)
            result = _map_files_to_features(
                ["src/FileDeliveryService.java", "src/FileDeliveryController.java"],
                skills_dir,
            )
            self.assertEqual(len(result["file-delivery"]), 2)

    def test_properties_file_matched(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            _write_skill(skills_dir, "file-delivery",
                         "Config: application.properties drives this feature.")
            result = _map_files_to_features(
                ["src/main/resources/application.properties"], skills_dir
            )
            self.assertIn("file-delivery", result)


# ---------------------------------------------------------------------------
# _resolve_skills_dir
# ---------------------------------------------------------------------------

class TestResolveSkillsDir(unittest.TestCase):
    def test_github_skills_preferred_over_root_skills(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / ".github" / "skills").mkdir(parents=True)
            (repo / "skills").mkdir()
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, repo / ".github" / "skills")

    def test_root_skills_returned_when_no_github_dir(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "skills").mkdir()
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, repo / "skills")

    def test_returns_none_when_neither_exists(self):
        with tempfile.TemporaryDirectory() as td:
            result = _resolve_skills_dir(Path(td))
            self.assertIsNone(result)

    def test_github_skills_only(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / ".github" / "skills").mkdir(parents=True)
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, repo / ".github" / "skills")


# ---------------------------------------------------------------------------
# ingest_responses (commit=False — no git required)
# ---------------------------------------------------------------------------

def _setup_repo(tmpdir: str, feature_id: str, version: int,
                response_content: str) -> tuple:
    """Create a minimal repo tree; return (repo_root, responses_dir)."""
    repo = Path(tmpdir)
    skill_path = repo / ".github" / "skills" / feature_id / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(_make_skill(feature_id, version=version), encoding="utf-8")

    responses_dir = repo / ".skill-gen" / ".update-responses"
    responses_dir.mkdir(parents=True)
    (responses_dir / f"{feature_id}.md").write_text(response_content, encoding="utf-8")
    return repo, responses_dir


class TestIngestResponses(unittest.TestCase):
    def test_version_bumped_in_written_skill(self):
        with tempfile.TemporaryDirectory() as td:
            feature = "file-delivery"
            response = _make_skill(feature, version=4)
            repo, rdir = _setup_repo(td, feature, version=3, response_content=response)
            result = ingest_responses(repo, responses_dir=rdir,
                                      commit=False, validate_schema=False)
            self.assertEqual(len(result.get("updated", [])), 1)
            written = (Path(td) / ".github" / "skills" / feature / "SKILL.md"
                       ).read_text(encoding="utf-8")
            self.assertIn("version: 4", written)

    def test_ingest_forces_correct_version_when_ai_skipped_bump(self):
        """If AI returned version: 3 (forgot to bump from 3), ingest must write 4."""
        with tempfile.TemporaryDirectory() as td:
            feature = "invoice-compare"
            response = _make_skill(feature, version=3)  # AI forgot to bump
            repo, rdir = _setup_repo(td, feature, version=3, response_content=response)
            result = ingest_responses(repo, responses_dir=rdir,
                                      commit=False, validate_schema=False)
            self.assertEqual(len(result.get("updated", [])), 1)
            written = (Path(td) / ".github" / "skills" / feature / "SKILL.md"
                       ).read_text(encoding="utf-8")
            self.assertIn("version: 4", written)

    def test_last_updated_set_to_today(self):
        with tempfile.TemporaryDirectory() as td:
            feature = "payment-method"
            response = _make_skill(feature, version=2)
            repo, rdir = _setup_repo(td, feature, version=1, response_content=response)
            ingest_responses(repo, responses_dir=rdir,
                             commit=False, validate_schema=False)
            written = (Path(td) / ".github" / "skills" / feature / "SKILL.md"
                       ).read_text(encoding="utf-8")
            today = date.today().isoformat()
            self.assertIn(f"last_updated: {today}", written)

    def test_missing_response_file_reported_as_failed(self):
        with tempfile.TemporaryDirectory() as td:
            feature = "missing-feature"
            repo = Path(td)
            skill_path = repo / ".github" / "skills" / feature / "SKILL.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text(_make_skill(feature, version=1), encoding="utf-8")
            rdir = repo / ".skill-gen" / ".update-responses"
            rdir.mkdir(parents=True)
            # No response file written for this feature
            result = ingest_responses(repo, responses_dir=rdir,
                                      commit=False, feature=feature,
                                      validate_schema=False)
            failed_ids = [f.get("feature") for f in result.get("failed", [])]
            self.assertIn(feature, failed_ids)

    def test_empty_response_reported_as_failed(self):
        with tempfile.TemporaryDirectory() as td:
            feature = "empty-response"
            repo, rdir = _setup_repo(td, feature, version=1,
                                     response_content="   \n  ")
            result = ingest_responses(repo, responses_dir=rdir,
                                      commit=False, validate_schema=False)
            failed_ids = [f.get("feature") for f in result.get("failed", [])]
            self.assertIn(feature, failed_ids)

    def test_missing_skill_md_reported_as_failed(self):
        with tempfile.TemporaryDirectory() as td:
            feature = "no-skill"
            repo = Path(td)
            (repo / ".github" / "skills").mkdir(parents=True)
            rdir = repo / ".skill-gen" / ".update-responses"
            rdir.mkdir(parents=True)
            (rdir / f"{feature}.md").write_text(_make_skill(feature), encoding="utf-8")
            result = ingest_responses(repo, responses_dir=rdir,
                                      commit=False, feature=feature,
                                      validate_schema=False)
            failed_ids = [f.get("feature") for f in result.get("failed", [])]
            self.assertIn(feature, failed_ids)

    def test_no_skills_dir_returns_early(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            result = ingest_responses(repo, commit=False, validate_schema=False)
            self.assertIn("reason", result)

    def test_fenced_response_content_unwrapped(self):
        """Responses wrapped in ```markdown fences are correctly stripped."""
        with tempfile.TemporaryDirectory() as td:
            feature = "file-delivery"
            raw_skill = _make_skill(feature, version=2)
            fenced = f"```markdown\n{raw_skill}\n```"
            repo, rdir = _setup_repo(td, feature, version=1, response_content=fenced)
            result = ingest_responses(repo, responses_dir=rdir,
                                      commit=False, validate_schema=False)
            self.assertEqual(len(result.get("updated", [])), 1)


if __name__ == "__main__":
    unittest.main()
