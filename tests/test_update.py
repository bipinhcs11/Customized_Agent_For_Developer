"""
Smoke tests for tools.skill_generator.update (Phase 2 incremental updater).

Covers:
  - _bump_version — version increment from existing frontmatter, defaulting
    to 1 when no version line is present
  - _domain_from_skill — reconstructing a minimal domain dict (classes,
    xmlSources, sqlSources, shellSources) from an existing SKILL.md's body
  - _resolve_skills_dir — prefers .github/skills over skills, returns None
    when neither exists
  - _map_files_to_features — maps changed file paths to feature ids by
    basename match against existing SKILL.mds, warns on unmatched files
  - _git_changed_files — git diff between two refs, with fallback to
    `git status --porcelain` when the diff range is invalid
  - emit_prompts / ingest_responses end-to-end — manual --feature trigger
    writes an update prompt, and ingesting a response bumps version and
    last_updated and writes the refreshed SKILL.md

All tests use stdlib only (tempfile, pathlib, subprocess, unittest).
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools.skill_generator.update import (
    _bump_version,
    _domain_from_skill,
    _git_changed_files,
    _map_files_to_features,
    _resolve_skills_dir,
    emit_prompts,
    ingest_responses,
)


def _write(repo: Path, rel: str, content: str) -> Path:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _make_skill(domain_id: str, version: int = 1) -> str:
    name = domain_id.title().replace("-", "")
    return f"""\
---
skill: {domain_id.replace('-', ' ').title()}
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
last_updated: 2026-01-01
---

# {domain_id.replace('-', ' ').title()}

## Purpose
Does something with {name}.java.

## Entry Points
- REST: GET /api/{domain_id} -> {name}Controller.get()

## Business Logic

### Core Flow
1. Receive -- {name}Controller.get()
2. Process -- {name}Service.process()

### Validation Rules
- Non-null -- {name}Service.validate()

### Business Rules
- Returns 200 -- {name}Service.process()

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| {name}Service.java | Service | core logic |

## Data Flow
```
GET /api/{domain_id}
   |
   v
{name}Service.process()
```

## Database & Storage
- Tables: {domain_id.replace('-', '_')}

## External Dependencies
none found

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| RuntimeException | failure | 500 |

## Edge Cases
- Null handled -- {name}Service.validate()

## Legacy Notes
none found

## Related Skills
none found

## AI Agent Instructions
1. Always validate -- {name}Service.validate()
"""


# ---------------------------------------------------------------------------
# _bump_version
# ---------------------------------------------------------------------------

class TestBumpVersion(unittest.TestCase):
    def test_increments_existing_version(self):
        old, new = _bump_version("---\nversion: 3\nskill: Foo\n---\n")
        self.assertEqual((old, new), (3, 4))

    def test_defaults_to_one_when_missing(self):
        old, new = _bump_version("---\nskill: Foo\n---\n")
        self.assertEqual((old, new), (1, 2))

    def test_only_matches_frontmatter_style_line(self):
        old, new = _bump_version("---\nversion: 12\nother: version: 99\n---\n")
        self.assertEqual((old, new), (12, 13))


# ---------------------------------------------------------------------------
# _domain_from_skill
# ---------------------------------------------------------------------------

class TestDomainFromSkill(unittest.TestCase):
    def test_extracts_classes_and_sources(self):
        skill_md = (
            "FooService.java handles things, see also BarController.java.\n"
            "Wired in applicationContext.xml and seeded by seed.sql, "
            "started via run.sh.\n"
        )
        domain = _domain_from_skill(skill_md, "file-delivery")

        self.assertEqual(domain["id"], "file-delivery")
        self.assertEqual(set(domain["classes"]), {"FooService", "BarController"})
        self.assertEqual(domain["xmlSources"], ["applicationContext.xml: from prior skill"])
        self.assertEqual(domain["sqlSources"], ["seed.sql: from prior skill"])
        self.assertEqual(domain["shellSources"], ["run.sh: from prior skill"])

    def test_no_sources_found(self):
        domain = _domain_from_skill("Nothing referenced here.", "empty-feature")
        self.assertEqual(domain["classes"], [])
        self.assertEqual(domain["xmlSources"], [])
        self.assertEqual(domain["sqlSources"], [])
        self.assertEqual(domain["shellSources"], [])


# ---------------------------------------------------------------------------
# _resolve_skills_dir
# ---------------------------------------------------------------------------

class TestResolveSkillsDir(unittest.TestCase):
    def test_prefers_github_skills(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / ".github" / "skills").mkdir(parents=True)
            (repo / "skills").mkdir()
            self.assertEqual(_resolve_skills_dir(repo), repo / ".github" / "skills")

    def test_falls_back_to_skills(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "skills").mkdir()
            self.assertEqual(_resolve_skills_dir(repo), repo / "skills")

    def test_returns_none_when_neither_exists(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(_resolve_skills_dir(Path(td)))


# ---------------------------------------------------------------------------
# _map_files_to_features
# ---------------------------------------------------------------------------

class TestMapFilesToFeatures(unittest.TestCase):
    def test_matches_by_basename(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            skills_dir = repo / ".github" / "skills"
            _write(skills_dir, "file-delivery/SKILL.md", _make_skill("file-delivery"))

            changed = ["src/main/java/com/acme/FileDeliveryService.java", "unrelated/Other.txt"]
            result = _map_files_to_features(changed, skills_dir)

            self.assertEqual(
                result, {"file-delivery": ["src/main/java/com/acme/FileDeliveryService.java"]}
            )

    def test_no_skills_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            result = _map_files_to_features(["Foo.java"], Path(td) / "missing")
            self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# _git_changed_files
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> None:
    # -c commit.gpgsign=false: these are throwaway fixture repos created
    # purely to exercise `git diff`/`git status`, not real project history.
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args],
        check=True, capture_output=True,
    )


class TestGitChangedFiles(unittest.TestCase):
    def test_diff_between_two_commits(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _git(repo, "init")
            _git(repo, "config", "user.email", "test@example.com")
            _git(repo, "config", "user.name", "Test")
            _write(repo, "a.java", "class A {}")
            _git(repo, "add", "a.java")
            _git(repo, "commit", "-m", "first")

            _write(repo, "b.java", "class B {}")
            _git(repo, "add", "b.java")
            _git(repo, "commit", "-m", "second")

            changed = _git_changed_files(repo, base="HEAD~1", head="HEAD")
            self.assertEqual(changed, ["b.java"])

    def test_falls_back_to_status_when_no_parent_commit(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _git(repo, "init")
            _git(repo, "config", "user.email", "test@example.com")
            _git(repo, "config", "user.name", "Test")
            _write(repo, "a.java", "class A {}")
            _git(repo, "add", "a.java")
            _git(repo, "commit", "-m", "first")

            _write(repo, "b.java", "class B {}")
            _git(repo, "add", "b.java")

            # HEAD~1 doesn't exist yet (single commit) -> diff fails -> fall
            # back to `git status --porcelain`, which shows the staged file.
            changed = _git_changed_files(repo, base="HEAD~1", head="HEAD")
            self.assertEqual(changed, ["b.java"])


# ---------------------------------------------------------------------------
# emit_prompts / ingest_responses end-to-end
# ---------------------------------------------------------------------------

class TestEmitAndIngest(unittest.TestCase):
    def _build_repo(self, repo: Path) -> None:
        _write(
            repo,
            "src/main/java/com/acme/FileDeliveryService.java",
            "package com.acme;\npublic class FileDeliveryService { public void process() {} }",
        )
        _write(repo, ".github/skills/file-delivery/SKILL.md", _make_skill("file-delivery"))

    def test_emit_writes_prompt_for_manual_feature(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self._build_repo(repo)

            result = emit_prompts(repo, feature="file-delivery")

            self.assertEqual(len(result["written"]), 1)
            prompt_path = Path(result["written"][0])
            self.assertTrue(prompt_path.exists())
            content = prompt_path.read_text(encoding="utf-8")
            self.assertIn("FileDeliveryService.java", content)
            self.assertIn("STAGE 3 GENERATE TEMPLATE", content)

    def test_emit_reports_missing_skill(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self._build_repo(repo)

            result = emit_prompts(repo, feature="does-not-exist")

            self.assertEqual(result["written"], [])
            self.assertEqual(len(result["failed"]), 1)
            self.assertEqual(result["failed"][0]["reason"], "skill not found")

    def test_ingest_bumps_version_and_date(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self._build_repo(repo)

            responses_dir = repo / ".skill-gen" / ".update-responses"
            responses_dir.mkdir(parents=True)
            # Response keeps version: 1 and a stale date -- ingest must force
            # both to the correct bumped value regardless of what the AI wrote.
            (responses_dir / "file-delivery.md").write_text(
                _make_skill("file-delivery", version=1), encoding="utf-8"
            )

            result = ingest_responses(repo, feature="file-delivery")

            self.assertEqual(result["failed"], [])
            self.assertEqual(len(result["updated"]), 1)
            updated_text = Path(result["updated"][0]).read_text(encoding="utf-8")
            self.assertRegex(updated_text, r"(?m)^version:\s*2$")
            self.assertIn(f"last_updated: {date.today().isoformat()}", updated_text)

    def test_ingest_rejects_invalid_response(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self._build_repo(repo)

            responses_dir = repo / ".skill-gen" / ".update-responses"
            responses_dir.mkdir(parents=True)
            (responses_dir / "file-delivery.md").write_text(
                "this is not a valid SKILL.md", encoding="utf-8"
            )

            result = ingest_responses(repo, feature="file-delivery")

            self.assertEqual(result["updated"], [])
            self.assertEqual(len(result["failed"]), 1)
            self.assertEqual(result["failed"][0]["reason"], "validation failed")


if __name__ == "__main__":
    unittest.main()
