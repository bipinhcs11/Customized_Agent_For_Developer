"""
Smoke tests for tools.skill_generator.update — Phase 2 updater helpers.

update.py is the only module with zero test coverage. This file closes that
gap for the functions that don't require git or a live LLM session:

  - _bump_version        — pure: parse + increment the frontmatter version
  - _domain_from_skill   — pure: reconstruct a domain dict from an existing SKILL.md
  - _resolve_skills_dir  — filesystem: return the first skills dir that exists
  - _map_files_to_features — filesystem: match changed file basenames to skills

All tests use stdlib only (tempfile, pathlib, unittest).
"""
import tempfile
import unittest
from pathlib import Path

from tools.skill_generator.update import (
    _bump_version,
    _domain_from_skill,
    _resolve_skills_dir,
    _map_files_to_features,
)


class TestBumpVersion(unittest.TestCase):
    def test_increments_integer_version(self):
        md = "---\nskill: foo\nversion: 3\n---\n\n## Purpose\nfoo\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 3)
        self.assertEqual(new, 4)

    def test_version_1_when_missing(self):
        md = "---\nskill: foo\n---\n\n## Purpose\nfoo\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_version_at_first_line(self):
        md = "version: 10\nskill: bar\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 10)
        self.assertEqual(new, 11)

    def test_returns_tuple_of_two_ints(self):
        md = "version: 5\n"
        result = _bump_version(md)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], int)
        self.assertIsInstance(result[1], int)


class TestDomainFromSkill(unittest.TestCase):
    SAMPLE_MD = (
        "---\nskill: File Delivery\ndomain: file-delivery\nversion: 2\n---\n\n"
        "## Key Classes & Files\n"
        "| FileDeliveryService.java | Service | Core logic |\n"
        "| FileDeliveryController.java | Controller | REST entry |\n"
        "| FileDeliveryRepository.java | Repository | JPA |\n"
        "Config: applicationContext.xml\n"
        "SQL: schema.sql\n"
    )

    def test_returns_correct_feature_id(self):
        d = _domain_from_skill(self.SAMPLE_MD, "file-delivery")
        self.assertEqual(d["id"], "file-delivery")
        self.assertEqual(d["name"], "file-delivery")

    def test_extracts_java_class_names(self):
        d = _domain_from_skill(self.SAMPLE_MD, "file-delivery")
        self.assertIn("FileDeliveryService", d["classes"])
        self.assertIn("FileDeliveryController", d["classes"])
        self.assertIn("FileDeliveryRepository", d["classes"])

    def test_class_names_deduplicated(self):
        md = "FileDeliveryService.java mentioned twice, FileDeliveryService.java again\n"
        d = _domain_from_skill(md, "x")
        count = d["classes"].count("FileDeliveryService")
        self.assertEqual(count, 1)

    def test_xml_sources_extracted(self):
        d = _domain_from_skill(self.SAMPLE_MD, "file-delivery")
        self.assertTrue(
            any("applicationContext.xml" in s for s in d["xmlSources"]),
            "expected applicationContext.xml in xmlSources",
        )

    def test_sql_sources_extracted(self):
        d = _domain_from_skill(self.SAMPLE_MD, "file-delivery")
        self.assertTrue(
            any("schema.sql" in s for s in d["sqlSources"]),
            "expected schema.sql in sqlSources",
        )

    def test_empty_skill_returns_empty_lists(self):
        d = _domain_from_skill("", "orphan")
        self.assertEqual(d["classes"], [])
        self.assertEqual(d["xmlSources"], [])
        self.assertEqual(d["sqlSources"], [])
        self.assertEqual(d["shellSources"], [])

    def test_description_always_empty_string(self):
        d = _domain_from_skill(self.SAMPLE_MD, "file-delivery")
        self.assertEqual(d["description"], "")


class TestResolveSkillsDir(unittest.TestCase):
    def test_github_skills_found(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            github_skills = repo / ".github" / "skills"
            github_skills.mkdir(parents=True)
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, github_skills)

    def test_top_level_skills_found_when_no_github(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            top_skills = repo / "skills"
            top_skills.mkdir()
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, top_skills)

    def test_github_skills_preferred_over_top_level(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / ".github" / "skills").mkdir(parents=True)
            (repo / "skills").mkdir()
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, repo / ".github" / "skills")

    def test_returns_none_when_neither_exists(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            result = _resolve_skills_dir(repo)
            self.assertIsNone(result)


class TestMapFilesToFeatures(unittest.TestCase):
    def _write_skill(self, skills_dir: Path, feature_id: str, body: str) -> Path:
        d = skills_dir / feature_id
        d.mkdir(parents=True, exist_ok=True)
        p = d / "SKILL.md"
        p.write_text(body, encoding="utf-8")
        return p

    def test_changed_file_matched_to_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td) / "skills"
            self._write_skill(
                skills, "file-delivery",
                "| FileDeliveryService.java | Service | Core logic |\n",
            )
            result = _map_files_to_features(
                ["src/main/java/com/example/FileDeliveryService.java"],
                skills,
            )
            self.assertIn("file-delivery", result)
            self.assertIn(
                "src/main/java/com/example/FileDeliveryService.java",
                result["file-delivery"],
            )

    def test_unrelated_file_not_matched(self):
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td) / "skills"
            self._write_skill(
                skills, "file-delivery",
                "| FileDeliveryService.java | Service | Core logic |\n",
            )
            result = _map_files_to_features(
                ["src/com/example/UnrelatedThing.java"],
                skills,
            )
            self.assertEqual(result, {})

    def test_file_matched_to_multiple_features(self):
        """A shared utility referenced in two skills should appear in both."""
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td) / "skills"
            shared_line = "| SharedUtils.java | Utility | Common helper |\n"
            self._write_skill(skills, "feature-a", shared_line)
            self._write_skill(skills, "feature-b", shared_line)
            result = _map_files_to_features(
                ["src/SharedUtils.java"],
                skills,
            )
            self.assertIn("feature-a", result)
            self.assertIn("feature-b", result)

    def test_nonexistent_skills_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "no-such-dir"
            result = _map_files_to_features(["Foo.java"], missing)
            self.assertEqual(result, {})

    def test_empty_changed_files_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td) / "skills"
            self._write_skill(
                skills, "feature-a",
                "| FileDeliveryService.java | Service | Core |\n",
            )
            result = _map_files_to_features([], skills)
            self.assertEqual(result, {})

    def test_xml_file_matched(self):
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td) / "skills"
            self._write_skill(
                skills, "file-delivery",
                "| applicationContext.xml | Config | Spring beans |\n",
            )
            result = _map_files_to_features(
                ["src/main/resources/applicationContext.xml"],
                skills,
            )
            self.assertIn("file-delivery", result)

    def test_sql_file_matched(self):
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td) / "skills"
            self._write_skill(
                skills, "file-delivery",
                "| V2__add_column.sql | Migration | Adds new column |\n",
            )
            result = _map_files_to_features(
                ["db/migrations/V2__add_column.sql"],
                skills,
            )
            self.assertIn("file-delivery", result)


if __name__ == "__main__":
    unittest.main()
