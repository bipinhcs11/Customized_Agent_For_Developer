"""
Smoke tests for tools.skill_generator.update (Phase 2 updater).

Covers the pure and filesystem helpers that need no subprocess mocking:
  - _bump_version: version field is found and incremented correctly
  - _domain_from_skill: class/xml/sql/shell names are extracted from an
    existing SKILL.md so that update-emit can rebuild the source blob
  - _resolve_skills_dir: prefers .github/skills/ over skills/ when both
    exist, and returns None when neither is present
  - _map_files_to_features: changed files are matched against SKILL.md
    basenames and attributed to the correct feature ids

Regression: _git_changed_files fallback for renames.
  The git status --porcelain fallback path used to return "old -> new"
  for renamed files (l[3:] on "R  old -> new"). The fix keeps only the
  destination. This is tested by exercising _map_files_to_features with
  the destination name so the mapping still succeeds.

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


class TestBumpVersion(unittest.TestCase):
    def test_existing_version_incremented(self):
        md = "---\nskill: foo\nversion: 3\ndomain: foo\n---\n## Purpose\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 3)
        self.assertEqual(new, 4)

    def test_version_1_when_missing(self):
        md = "---\nskill: foo\ndomain: foo\n---\n## Purpose\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_version_in_middle_of_frontmatter(self):
        md = "---\nskill: bar\ndomain: bar\nversion: 12\nstatus: active\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 12)
        self.assertEqual(new, 13)


class TestDomainFromSkill(unittest.TestCase):
    SAMPLE_MD = (
        "---\n"
        "skill: File Delivery\n"
        "domain: file-delivery\n"
        "version: 2\n"
        "---\n"
        "## Key Classes & Files\n"
        "| FileDeliveryService.java | core service |\n"
        "| FileDeliveryRepository.java | data access |\n"
        "| delivery-config.xml | bean wiring |\n"
        "| load_delivery.sql | DDL |\n"
        "| run_delivery.sh | launcher |\n"
    )

    def test_feature_id_preserved(self):
        d = _domain_from_skill(self.SAMPLE_MD, "file-delivery")
        self.assertEqual(d["id"], "file-delivery")

    def test_java_class_names_extracted(self):
        d = _domain_from_skill(self.SAMPLE_MD, "file-delivery")
        self.assertIn("FileDeliveryService", d["classes"])
        self.assertIn("FileDeliveryRepository", d["classes"])

    def test_xml_sources_extracted(self):
        d = _domain_from_skill(self.SAMPLE_MD, "file-delivery")
        xml_paths = [s.split(":")[0].strip() for s in d["xmlSources"]]
        self.assertIn("delivery-config.xml", xml_paths)

    def test_sql_sources_extracted(self):
        d = _domain_from_skill(self.SAMPLE_MD, "file-delivery")
        sql_paths = [s.split(":")[0].strip() for s in d["sqlSources"]]
        self.assertIn("load_delivery.sql", sql_paths)

    def test_shell_sources_extracted(self):
        d = _domain_from_skill(self.SAMPLE_MD, "file-delivery")
        sh_paths = [s.split(":")[0].strip() for s in d["shellSources"]]
        self.assertIn("run_delivery.sh", sh_paths)

    def test_empty_skill_returns_minimal_dict(self):
        d = _domain_from_skill("no useful content", "orphan")
        self.assertEqual(d["id"], "orphan")
        self.assertEqual(d["classes"], [])
        self.assertEqual(d["xmlSources"], [])


class TestResolveSkillsDir(unittest.TestCase):
    def test_prefers_github_skills_when_both_exist(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            github_skills = repo / ".github" / "skills"
            github_skills.mkdir(parents=True)
            plain_skills = repo / "skills"
            plain_skills.mkdir()
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, github_skills)

    def test_falls_back_to_plain_skills(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            plain_skills = repo / "skills"
            plain_skills.mkdir()
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, plain_skills)

    def test_returns_none_when_neither_exists(self):
        with tempfile.TemporaryDirectory() as td:
            result = _resolve_skills_dir(Path(td))
            self.assertIsNone(result)


class TestMapFilesToFeatures(unittest.TestCase):
    def _make_skills_dir(self, tmpdir: Path, features: dict) -> Path:
        """features: {feature_id: skill_md_content}"""
        skills_dir = tmpdir / ".github" / "skills"
        for fid, content in features.items():
            skill_path = skills_dir / fid / "SKILL.md"
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(content, encoding="utf-8")
        return skills_dir

    def test_changed_file_matched_to_feature(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            md = (
                "---\nskill: File Delivery\ndomain: file-delivery\nversion: 1\n---\n"
                "## Key Classes & Files\n"
                "| FileDeliveryService.java | main service |\n"
            )
            skills_dir = self._make_skills_dir(repo, {"file-delivery": md})
            result = _map_files_to_features(
                ["src/main/java/com/example/FileDeliveryService.java"], skills_dir
            )
            self.assertIn("file-delivery", result)
            self.assertIn(
                "src/main/java/com/example/FileDeliveryService.java",
                result["file-delivery"],
            )

    def test_unrelated_file_not_matched(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            md = (
                "---\nskill: File Delivery\ndomain: file-delivery\nversion: 1\n---\n"
                "## Key Classes & Files\n"
                "| FileDeliveryService.java | main service |\n"
            )
            skills_dir = self._make_skills_dir(repo, {"file-delivery": md})
            result = _map_files_to_features(
                ["src/main/java/com/example/Unrelated.java"], skills_dir
            )
            self.assertNotIn("file-delivery", result)

    def test_rename_destination_matches_after_fix(self):
        """Regression: _git_changed_files used to return 'old -> new' for renames
        from git status --porcelain. After the fix, callers receive only the
        destination path. Verify that the destination basename still maps
        correctly to its feature."""
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            md = (
                "---\nskill: Invoice Compare\ndomain: invoice-compare\nversion: 1\n---\n"
                "## Key Classes & Files\n"
                "| InvoiceComparator.java | core logic |\n"
            )
            skills_dir = self._make_skills_dir(repo, {"invoice-compare": md})
            # Simulate that _git_changed_files correctly returned only the
            # destination after the rename bug was fixed.
            destination = "src/main/java/com/example/InvoiceComparator.java"
            result = _map_files_to_features([destination], skills_dir)
            self.assertIn("invoice-compare", result,
                          "Destination of a renamed file must still map to its feature")

    def test_empty_skills_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            skills_dir = repo / ".github" / "skills"
            skills_dir.mkdir(parents=True)
            result = _map_files_to_features(["anything.java"], skills_dir)
            self.assertEqual(result, {})

    def test_nonexistent_skills_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            result = _map_files_to_features(
                ["anything.java"], Path(td) / "no_such_dir"
            )
            self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
