"""
Smoke tests for tools.skill_generator.update — the Phase-2 incremental updater.

Covers the pure helper functions and the ingest_responses integration path.
The two network-touching operations (_git_changed_files and emit_prompts's
subprocess calls) are not covered here — they require a real git repo and
are exercised in manual QA.

Covered:
  - _bump_version: normal bump, version 1, missing version line
  - _resolve_skills_dir: .github/skills/, skills/, neither, both present
  - _domain_from_skill: minimal text, .java mentions, .xml/.sql/.sh mentions
  - _map_files_to_features: happy path, unknown file, missing skills dir,
      file claimed by two SKILL.mds
  - ingest_responses: version bumped, last_updated replaced, file written;
      missing skills dir; missing response file; empty response;
      commit=False default (no git invocation)

All tests use stdlib only (tempfile, pathlib, re, unittest).
"""
import re
import tempfile
import unittest
from pathlib import Path

from tools.skill_generator.update import (
    _bump_version,
    _domain_from_skill,
    _map_files_to_features,
    _resolve_skills_dir,
    ingest_responses,
)


# ─── Minimal valid SKILL.md template ─────────────────────────────────────────

def _make_skill(domain_id: str, version: int = 1,
                extra_files: str = "") -> str:
    """Build a minimal but validator-clean SKILL.md for testing."""
    title = domain_id.replace("-", " ").title()
    cls = domain_id.replace("-", "").title()
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
last_updated: 2020-01-01
---

# {title}

## Purpose
Does something.

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
| config.xml | Config | wiring |
| schema.sql | SQL | DDL |
| run.sh | Shell | launcher |
{extra_files}

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


# ─────────────────────────────────────────────────────────────────────────────
# _bump_version
# ─────────────────────────────────────────────────────────────────────────────

class TestBumpVersion(unittest.TestCase):
    def test_increments_version(self):
        md = "---\nskill: Foo\nversion: 3\ndomain: foo\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 3)
        self.assertEqual(new, 4)

    def test_version_one_to_two(self):
        md = "---\nversion: 1\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_missing_version_defaults_to_one(self):
        md = "---\nskill: Foo\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_large_version_number(self):
        md = "---\nversion: 99\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 99)
        self.assertEqual(new, 100)

    def test_version_not_confused_by_other_digits(self):
        # A line like "java_version: 17" must not be confused with "version:"
        md = "---\njava_version: 17\nversion: 5\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 5)
        self.assertEqual(new, 6)


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_skills_dir
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveSkillsDir(unittest.TestCase):
    def test_github_skills_found(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            d = repo / ".github" / "skills"
            d.mkdir(parents=True)
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, d)

    def test_skills_at_root_found(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            d = repo / "skills"
            d.mkdir()
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, d)

    def test_neither_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            result = _resolve_skills_dir(repo)
            self.assertIsNone(result)

    def test_github_skills_preferred_when_both_exist(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / ".github" / "skills").mkdir(parents=True)
            (repo / "skills").mkdir()
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, repo / ".github" / "skills")


# ─────────────────────────────────────────────────────────────────────────────
# _domain_from_skill
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainFromSkill(unittest.TestCase):
    def test_id_and_name_match_feature_id(self):
        d = _domain_from_skill("## some content", "file-delivery")
        self.assertEqual(d["id"], "file-delivery")
        self.assertEqual(d["name"], "file-delivery")

    def test_java_class_extracted(self):
        md = _make_skill("file-delivery")
        d = _domain_from_skill(md, "file-delivery")
        # _make_skill puts "FiledeliveryService.java" and similar in Key Classes
        self.assertTrue(len(d["classes"]) >= 1)
        # All entries must be CapitalizedNames (the regex: [A-Z][A-Za-z0-9]+\.java)
        for cls in d["classes"]:
            self.assertRegex(cls, r"^[A-Z][A-Za-z0-9]+$")

    def test_xml_source_extracted(self):
        md = _make_skill("file-delivery")
        d = _domain_from_skill(md, "file-delivery")
        self.assertTrue(
            any("config.xml" in x for x in d.get("xmlSources", [])),
            "config.xml mentioned in SKILL.md should appear in xmlSources",
        )

    def test_sql_source_extracted(self):
        md = _make_skill("file-delivery")
        d = _domain_from_skill(md, "file-delivery")
        self.assertTrue(
            any("schema.sql" in x for x in d.get("sqlSources", [])),
            "schema.sql mentioned in SKILL.md should appear in sqlSources",
        )

    def test_shell_source_extracted(self):
        md = _make_skill("file-delivery")
        d = _domain_from_skill(md, "file-delivery")
        self.assertTrue(
            any("run.sh" in x for x in d.get("shellSources", [])),
            "run.sh mentioned in SKILL.md should appear in shellSources",
        )

    def test_empty_skill_md_does_not_crash(self):
        d = _domain_from_skill("", "empty-feature")
        self.assertEqual(d["id"], "empty-feature")
        self.assertEqual(d["classes"], [])
        self.assertEqual(d["xmlSources"], [])
        self.assertEqual(d["sqlSources"], [])
        self.assertEqual(d["shellSources"], [])

    def test_description_is_empty_string(self):
        d = _domain_from_skill("some text", "my-feature")
        self.assertEqual(d["description"], "")


# ─────────────────────────────────────────────────────────────────────────────
# _map_files_to_features
# ─────────────────────────────────────────────────────────────────────────────

class TestMapFilesToFeatures(unittest.TestCase):
    def _setup_skills_dir(self, td: str, skills: dict) -> Path:
        """skills: {feature_id: skill_md_text}"""
        skills_dir = Path(td) / "skills"
        for fid, text in skills.items():
            d = skills_dir / fid
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(text, encoding="utf-8")
        return skills_dir

    def test_known_file_maps_to_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup_skills_dir(td, {
                "file-delivery": _make_skill("file-delivery"),
            })
            # FiledeliveryService.java is referenced in the SKILL.md
            result = _map_files_to_features(
                ["src/main/java/FiledeliveryService.java"], skills_dir
            )
            self.assertIn("file-delivery", result)

    def test_unknown_file_not_mapped(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup_skills_dir(td, {
                "file-delivery": _make_skill("file-delivery"),
            })
            result = _map_files_to_features(
                ["src/main/java/Unrelated.java"], skills_dir
            )
            self.assertEqual(result, {})

    def test_missing_skills_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "nonexistent"
            result = _map_files_to_features(["anything.java"], skills_dir)
            self.assertEqual(result, {})

    def test_file_claimed_by_two_features(self):
        shared_file = "Shared.java"
        skill_a = _make_skill("feature-a") + f"| {shared_file} | Util | shared |\n"
        skill_b = _make_skill("feature-b") + f"| {shared_file} | Util | shared |\n"
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup_skills_dir(td, {
                "feature-a": skill_a,
                "feature-b": skill_b,
            })
            result = _map_files_to_features([f"src/{shared_file}"], skills_dir)
            self.assertIn("feature-a", result)
            self.assertIn("feature-b", result)

    def test_empty_changed_files_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup_skills_dir(td, {
                "file-delivery": _make_skill("file-delivery"),
            })
            result = _map_files_to_features([], skills_dir)
            self.assertEqual(result, {})


# ─────────────────────────────────────────────────────────────────────────────
# ingest_responses
# ─────────────────────────────────────────────────────────────────────────────

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestIngestResponsesHappyPath(unittest.TestCase):
    """ingest_responses reads a response file, bumps version, updates
    last_updated, and writes the result back to the SKILL.md."""

    def _run(self, td: str, feature_id: str,
             original_version: int = 1) -> tuple:
        repo = Path(td)
        skills_dir = repo / "skills"
        responses_dir = repo / ".skill-gen" / ".update-responses"

        existing_md = _make_skill(feature_id, version=original_version)
        _write(skills_dir / feature_id / "SKILL.md", existing_md)

        # The response has the same content (version/last_updated will be overwritten)
        _write(responses_dir / f"{feature_id}.md", existing_md)

        result = ingest_responses(
            repo,
            responses_dir=responses_dir,
            commit=False,
            validate_schema=False,
        )
        return result, skills_dir / feature_id / "SKILL.md"

    def test_skill_written_to_disk(self):
        with tempfile.TemporaryDirectory() as td:
            result, skill_path = self._run(td, "file-delivery")
            self.assertEqual(len(result["updated"]), 1)
            self.assertTrue(skill_path.exists())

    def test_version_bumped(self):
        with tempfile.TemporaryDirectory() as td:
            result, skill_path = self._run(td, "file-delivery", original_version=3)
            content = skill_path.read_text(encoding="utf-8")
            m = re.search(r"^version:\s*(\d+)", content, re.MULTILINE)
            self.assertIsNotNone(m)
            self.assertEqual(int(m.group(1)), 4)

    def test_last_updated_set_to_today(self):
        from datetime import date
        today = date.today().isoformat()
        with tempfile.TemporaryDirectory() as td:
            result, skill_path = self._run(td, "file-delivery")
            content = skill_path.read_text(encoding="utf-8")
            self.assertIn(f"last_updated: {today}", content)

    def test_failed_list_empty_on_success(self):
        with tempfile.TemporaryDirectory() as td:
            result, _ = self._run(td, "file-delivery")
            self.assertEqual(result["failed"], [])


class TestIngestResponsesNoSkillsDir(unittest.TestCase):
    def test_returns_error_when_no_skills_dir(self):
        with tempfile.TemporaryDirectory() as td:
            result = ingest_responses(Path(td), commit=False, validate_schema=False)
            self.assertIn("reason", result)
            self.assertEqual(result["updated"], [])


class TestIngestResponsesMissingResponseFile(unittest.TestCase):
    def test_missing_response_goes_to_failed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            skills_dir = repo / "skills"
            _write(
                skills_dir / "file-delivery" / "SKILL.md",
                _make_skill("file-delivery"),
            )
            # responses_dir exists but is empty
            responses_dir = repo / ".skill-gen" / ".update-responses"
            responses_dir.mkdir(parents=True)

            result = ingest_responses(
                repo,
                responses_dir=responses_dir,
                feature="file-delivery",
                commit=False,
                validate_schema=False,
            )
            self.assertEqual(len(result["failed"]), 1)
            self.assertEqual(result["failed"][0]["feature"], "file-delivery")


class TestIngestResponsesEmptyResponse(unittest.TestCase):
    def test_empty_response_goes_to_failed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            skills_dir = repo / "skills"
            responses_dir = repo / ".skill-gen" / ".update-responses"

            _write(skills_dir / "file-delivery" / "SKILL.md", _make_skill("file-delivery"))
            _write(responses_dir / "file-delivery.md", "   \n   ")

            result = ingest_responses(
                repo,
                responses_dir=responses_dir,
                commit=False,
                validate_schema=False,
            )
            self.assertEqual(len(result["updated"]), 0)
            self.assertEqual(len(result["failed"]), 1)


class TestIngestResponsesMarkdownFenceStripped(unittest.TestCase):
    def test_fenced_response_written_without_fence(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            skills_dir = repo / "skills"
            responses_dir = repo / ".skill-gen" / ".update-responses"

            _write(skills_dir / "file-delivery" / "SKILL.md", _make_skill("file-delivery"))
            # Wrap the response in a markdown code fence (common host-agent output)
            fenced = "```markdown\n" + _make_skill("file-delivery", version=2) + "\n```"
            _write(responses_dir / "file-delivery.md", fenced)

            result = ingest_responses(
                repo,
                responses_dir=responses_dir,
                commit=False,
                validate_schema=False,
            )
            self.assertEqual(len(result["updated"]), 1)
            content = (skills_dir / "file-delivery" / "SKILL.md").read_text()
            self.assertNotIn("```", content.split("---")[0])  # no fence in frontmatter


class TestIngestResponsesFeatureFilter(unittest.TestCase):
    def test_feature_flag_restricts_to_single_feature(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            skills_dir = repo / "skills"
            responses_dir = repo / ".skill-gen" / ".update-responses"

            _write(skills_dir / "feature-a" / "SKILL.md", _make_skill("feature-a"))
            _write(skills_dir / "feature-b" / "SKILL.md", _make_skill("feature-b"))
            _write(responses_dir / "feature-a.md", _make_skill("feature-a", version=2))
            _write(responses_dir / "feature-b.md", _make_skill("feature-b", version=2))

            result = ingest_responses(
                repo,
                responses_dir=responses_dir,
                feature="feature-a",
                commit=False,
                validate_schema=False,
            )
            updated_names = [Path(p).parent.name for p in result["updated"]]
            self.assertIn("feature-a", updated_names)
            self.assertNotIn("feature-b", updated_names)


if __name__ == "__main__":
    unittest.main()
