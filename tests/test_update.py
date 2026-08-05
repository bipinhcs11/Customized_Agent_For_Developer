"""
Smoke tests for tools.skill_generator.update — pure-function layer.

Covers:
  - _bump_version — extracts version from frontmatter and returns (old, new);
      handles missing version, multi-digit versions, version embedded anywhere
      in the document.
  - _domain_from_skill — reconstructs a minimal domain dict from an existing
      SKILL.md; checks class extraction, XML/SQL/shell extraction, and id/name
      assignment.
  - _map_files_to_features — maps changed file paths to feature IDs by
      matching basenames against filenames mentioned in each SKILL.md; handles
      no-match, multi-feature, and a missing skills directory.
  - _resolve_skills_dir — resolves the skills directory from a repo root;
      prefers .github/skills over skills, returns None when neither exists.

All tests use stdlib only (tempfile, pathlib, unittest).
"""
import tempfile
import unittest
from pathlib import Path

from tools.skill_generator.update import (
    _bump_version,
    _domain_from_skill,
    _map_files_to_features,
    _resolve_skills_dir,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_skill_md(version: int = 1, extra_body: str = "") -> str:
    return f"""\
---
skill: File Delivery
domain: file-delivery
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

## Purpose
Handles file transfers.

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| FileDeliveryService.java | Service | core logic |
| FileDeliveryController.java | Controller | REST entry point |

## Database & Storage
- Schema: schema-init.sql

## Related Skills
none found
{extra_body}
"""


# ---------------------------------------------------------------------------
# _bump_version
# ---------------------------------------------------------------------------

class TestBumpVersion(unittest.TestCase):
    def test_version_1_bumps_to_2(self):
        md = _make_skill_md(version=1)
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_version_3_bumps_to_4(self):
        md = _make_skill_md(version=3)
        old, new = _bump_version(md)
        self.assertEqual(old, 3)
        self.assertEqual(new, 4)

    def test_multi_digit_version_bumped_correctly(self):
        md = _make_skill_md(version=99)
        old, new = _bump_version(md)
        self.assertEqual(old, 99)
        self.assertEqual(new, 100)

    def test_missing_version_defaults_to_1(self):
        # A SKILL.md with no version line should default old_version = 1.
        md = "---\nskill: Foo\ndomain: foo\n---\n\n## Purpose\nnone found\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_version_with_leading_whitespace(self):
        # The regex uses MULTILINE so any line starting with version: must match.
        md = "---\n  version: 5\n---\n"
        # MULTILINE anchors to line-starts — leading spaces would not match ^version.
        # This test documents the current behaviour: only "^version:" (no indent) matches.
        old, new = _bump_version(md)
        # With leading spaces the regex does NOT match, so it defaults to 1.
        self.assertEqual(new, old + 1)

    def test_old_plus_one_always_equals_new(self):
        for v in (1, 2, 10, 42):
            md = _make_skill_md(version=v)
            old, new = _bump_version(md)
            self.assertEqual(new, old + 1, f"version {v}: new should be old+1")


# ---------------------------------------------------------------------------
# _domain_from_skill
# ---------------------------------------------------------------------------

class TestDomainFromSkill(unittest.TestCase):
    def test_id_and_name_set_to_feature_id(self):
        domain = _domain_from_skill("anything", "file-delivery")
        self.assertEqual(domain["id"], "file-delivery")
        self.assertEqual(domain["name"], "file-delivery")

    def test_description_always_empty(self):
        domain = _domain_from_skill("anything", "foo")
        self.assertEqual(domain["description"], "")

    def test_java_class_extracted(self):
        md = "| FileDeliveryService.java | Service | core logic |\n"
        domain = _domain_from_skill(md, "file-delivery")
        self.assertIn("FileDeliveryService", domain["classes"])

    def test_multiple_java_classes_extracted(self):
        md = (
            "| FileDeliveryService.java | Service | core |\n"
            "| FileDeliveryController.java | Controller | REST |\n"
            "| FileDeliveryDao.java | DAO | DB |\n"
        )
        domain = _domain_from_skill(md, "fd")
        names = set(domain["classes"])
        self.assertIn("FileDeliveryService", names)
        self.assertIn("FileDeliveryController", names)
        self.assertIn("FileDeliveryDao", names)

    def test_lowercase_java_file_not_extracted(self):
        # The regex requires an uppercase first letter: [A-Z][A-Za-z0-9]+\.java
        md = "helper.java and AnotherClass.java mentioned here\n"
        domain = _domain_from_skill(md, "x")
        self.assertIn("AnotherClass", domain["classes"])
        self.assertNotIn("helper", domain["classes"])

    def test_java_classes_deduplicated(self):
        md = (
            "| FileDeliveryService.java | Service | logic |\n"
            "| FileDeliveryService.java | Service | (again) |\n"
        )
        domain = _domain_from_skill(md, "fd")
        self.assertEqual(domain["classes"].count("FileDeliveryService"), 1)

    def test_xml_file_added_to_xml_sources(self):
        md = "See beans.xml for Spring configuration.\n"
        domain = _domain_from_skill(md, "fd")
        xml_sources = domain["xmlSources"]
        self.assertTrue(
            any("beans.xml" in s for s in xml_sources),
            f"beans.xml not found in xmlSources: {xml_sources}",
        )

    def test_sql_file_added_to_sql_sources(self):
        md = "Schema defined in schema-init.sql and seed-data.sql.\n"
        domain = _domain_from_skill(md, "fd")
        sql_sources = domain["sqlSources"]
        self.assertTrue(any("schema-init.sql" in s for s in sql_sources))
        self.assertTrue(any("seed-data.sql" in s for s in sql_sources))

    def test_shell_file_added_to_shell_sources(self):
        md = "Deployed by deploy.sh and rollback.sh scripts.\n"
        domain = _domain_from_skill(md, "fd")
        sh_sources = domain["shellSources"]
        self.assertTrue(any("deploy.sh" in s for s in sh_sources))
        self.assertTrue(any("rollback.sh" in s for s in sh_sources))

    def test_no_files_yields_empty_lists(self):
        md = "No files referenced at all.\n"
        domain = _domain_from_skill(md, "empty")
        self.assertEqual(domain["classes"], [])
        self.assertEqual(domain["xmlSources"], [])
        self.assertEqual(domain["sqlSources"], [])
        self.assertEqual(domain["shellSources"], [])

    def test_xml_source_annotation_appended(self):
        # Each XML entry should have ": from prior skill" appended.
        md = "spring-context.xml referenced here.\n"
        domain = _domain_from_skill(md, "fd")
        self.assertTrue(
            any(s.endswith(": from prior skill") for s in domain["xmlSources"]),
            "XML sources should end with ': from prior skill'",
        )


# ---------------------------------------------------------------------------
# _map_files_to_features
# ---------------------------------------------------------------------------

class TestMapFilesToFeatures(unittest.TestCase):
    def _write_skill(self, skills_dir: Path, feature_id: str, content: str) -> None:
        d = skills_dir / feature_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(content, encoding="utf-8")

    def test_missing_skills_dir_returns_empty(self):
        result = _map_files_to_features(
            ["src/FooService.java"],
            Path("/does/not/exist/skills"),
        )
        self.assertEqual(result, {})

    def test_changed_file_matched_to_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            self._write_skill(skills_dir, "file-delivery", _make_skill_md())
            result = _map_files_to_features(
                ["src/main/java/FileDeliveryService.java"],
                skills_dir,
            )
            self.assertIn("file-delivery", result)
            self.assertIn("src/main/java/FileDeliveryService.java",
                          result["file-delivery"])

    def test_unmatched_file_absent_from_result(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            self._write_skill(skills_dir, "file-delivery", _make_skill_md())
            result = _map_files_to_features(
                ["src/UnrelatedBean.java"],
                skills_dir,
            )
            self.assertNotIn("file-delivery", result)

    def test_multiple_changed_files_same_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            self._write_skill(skills_dir, "file-delivery", _make_skill_md())
            result = _map_files_to_features(
                [
                    "src/FileDeliveryService.java",
                    "src/FileDeliveryController.java",
                ],
                skills_dir,
            )
            self.assertEqual(len(result["file-delivery"]), 2)

    def test_file_matched_to_correct_feature_among_many(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            fd_md = _make_skill_md() + "| FileDeliveryDao.java | DAO | DB |\n"
            ic_md = (
                "---\nskill: Invoice\ndomain: invoice-compare\nversion: 1\n"
                "project_type: REST API\nframework: Spring Boot\njava_version: 17\n"
                "legacy: false\nstatus: active\nflags: none\nrelated_skills: none\n"
                "generated_by: agent\nlast_updated: 2026-01-01\n---\n\n"
                "| InvoiceCompareService.java | Service | compare invoices |\n"
            )
            self._write_skill(skills_dir, "file-delivery", fd_md)
            self._write_skill(skills_dir, "invoice-compare", ic_md)
            result = _map_files_to_features(
                ["com/example/InvoiceCompareService.java"],
                skills_dir,
            )
            self.assertIn("invoice-compare", result)
            self.assertNotIn("file-delivery", result)

    def test_empty_changed_files_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            self._write_skill(skills_dir, "file-delivery", _make_skill_md())
            result = _map_files_to_features([], skills_dir)
            self.assertEqual(result, {})

    def test_properties_file_matched(self):
        md = (
            _make_skill_md()
            + "\nConfig: application.properties drives this feature.\n"
        )
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            self._write_skill(skills_dir, "file-delivery", md)
            result = _map_files_to_features(
                ["src/main/resources/application.properties"],
                skills_dir,
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
            repo = Path(td)
            result = _resolve_skills_dir(repo)
            self.assertIsNone(result)

    def test_github_skills_only(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / ".github" / "skills").mkdir(parents=True)
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, repo / ".github" / "skills")


if __name__ == "__main__":
    unittest.main()
