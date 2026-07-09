"""
Smoke tests for tools.skill_generator.update — the Phase 2 incremental updater.

Covers the pure helper functions that can be exercised without a live git
repo or a host agent session:

  _bump_version          — extracts and increments the SKILL.md version field
  _domain_from_skill     — reconstructs a minimal domain dict from an existing SKILL.md
  _resolve_skills_dir    — finds the active skills directory in a repo
  _map_files_to_features — maps changed file basenames to affected feature IDs

All tests use stdlib only (tempfile, pathlib, unittest).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.skill_generator.update import (
    _bump_version,
    _domain_from_skill,
    _map_files_to_features,
    _resolve_skills_dir,
)


# ─────────────────────────────────────────────────────────────────────────────
# _bump_version
# ─────────────────────────────────────────────────────────────────────────────

class TestBumpVersion(unittest.TestCase):
    def test_increments_version_1(self):
        md = "---\nversion: 1\nskill: foo\n---\n\n## Purpose\nnone found\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_increments_arbitrary_version(self):
        md = "---\nversion: 7\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 7)
        self.assertEqual(new, 8)

    def test_missing_version_defaults_to_1(self):
        # When there is no version field, _bump_version treats it as 1.
        md = "---\nskill: foo\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_version_with_extra_whitespace(self):
        md = "---\nversion:   3\n---\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 3)
        self.assertEqual(new, 4)


# ─────────────────────────────────────────────────────────────────────────────
# _domain_from_skill
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainFromSkill(unittest.TestCase):
    def test_feature_id_becomes_domain_id(self):
        md = "---\nskill: Foo\n---\nnone found\n"
        d = _domain_from_skill(md, "my-feature")
        self.assertEqual(d["id"], "my-feature")
        self.assertEqual(d["name"], "my-feature")

    def test_extracts_java_class_names(self):
        md = (
            "---\nskill: Foo\n---\n"
            "## Key Classes & Files\n"
            "| FooService.java | Service | core logic |\n"
            "| FooController.java | Controller | REST endpoint |\n"
        )
        d = _domain_from_skill(md, "foo")
        self.assertIn("FooService", d["classes"])
        self.assertIn("FooController", d["classes"])

    def test_extracts_xml_sources(self):
        md = (
            "---\nskill: Foo\n---\n"
            "## Key Classes & Files\n"
            "| applicationContext.xml | Spring config | bean wiring |\n"
        )
        d = _domain_from_skill(md, "foo")
        xml_refs = " ".join(d["xmlSources"])
        self.assertIn("applicationContext.xml", xml_refs)

    def test_extracts_sql_sources(self):
        md = (
            "---\nskill: Foo\n---\n"
            "## Database & Storage\n"
            "Migrations: V1__create_orders.sql applies the initial DDL.\n"
        )
        d = _domain_from_skill(md, "foo")
        sql_refs = " ".join(d["sqlSources"])
        self.assertIn("V1__create_orders.sql", sql_refs)

    def test_extracts_shell_sources(self):
        md = "---\nskill: Foo\n---\nThe deploy.sh script bootstraps the batch run.\n"
        d = _domain_from_skill(md, "foo")
        sh_refs = " ".join(d["shellSources"])
        self.assertIn("deploy.sh", sh_refs)

    def test_empty_skill_md_returns_empty_lists(self):
        md = "---\nskill: Foo\n---\nnone found\n"
        d = _domain_from_skill(md, "empty-feature")
        self.assertEqual(d["classes"], [])
        self.assertEqual(d["xmlSources"], [])
        self.assertEqual(d["sqlSources"], [])
        self.assertEqual(d["shellSources"], [])

    def test_description_is_empty_string(self):
        # _domain_from_skill sets description to "" — callers may fill it later.
        md = "---\nskill: Foo\n---\nnone found\n"
        d = _domain_from_skill(md, "foo")
        self.assertEqual(d["description"], "")


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_skills_dir
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveSkillsDir(unittest.TestCase):
    def test_github_skills_found(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            github_skills = repo / ".github" / "skills"
            github_skills.mkdir(parents=True)
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, github_skills)

    def test_plain_skills_found_as_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            plain = repo / "skills"
            plain.mkdir()
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, plain)

    def test_github_skills_preferred_over_plain(self):
        # When both exist, .github/skills takes priority (checked first in candidates).
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            github_skills = repo / ".github" / "skills"
            github_skills.mkdir(parents=True)
            plain = repo / "skills"
            plain.mkdir()
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, github_skills)

    def test_neither_exists_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            result = _resolve_skills_dir(Path(td))
            self.assertIsNone(result)


# ─────────────────────────────────────────────────────────────────────────────
# _map_files_to_features
# ─────────────────────────────────────────────────────────────────────────────

def _write_minimal_skill(skills_dir: Path, feature_id: str, mentioned_files: list) -> None:
    """Write a minimal SKILL.md that mentions the given filenames so that
    _map_files_to_features can find them via basename matching."""
    skill_dir = skills_dir / feature_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"---\nskill: {feature_id}\n---\n"]
    for fname in mentioned_files:
        lines.append(f"| {fname} | class | role |\n")
    (skill_dir / "SKILL.md").write_text("".join(lines), encoding="utf-8")


class TestMapFilesToFeatures(unittest.TestCase):
    def test_changed_file_maps_to_matching_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            _write_minimal_skill(skills_dir, "file-delivery", ["FileDeliveryService.java"])

            result = _map_files_to_features(
                ["src/main/java/com/example/FileDeliveryService.java"], skills_dir
            )

            self.assertIn("file-delivery", result)
            self.assertIn(
                "src/main/java/com/example/FileDeliveryService.java",
                result["file-delivery"],
            )

    def test_unmatched_file_not_in_result(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            _write_minimal_skill(skills_dir, "foo", ["FooService.java"])

            result = _map_files_to_features(["BarService.java"], skills_dir)
            self.assertNotIn("foo", result)

    def test_file_matching_two_features_maps_to_both(self):
        # Same basename in two skills — both are returned (conservative).
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            _write_minimal_skill(skills_dir, "alpha", ["Shared.java"])
            _write_minimal_skill(skills_dir, "beta", ["Shared.java"])

            result = _map_files_to_features(["src/Shared.java"], skills_dir)
            self.assertIn("alpha", result)
            self.assertIn("beta", result)

    def test_empty_skills_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            skills_dir.mkdir()

            result = _map_files_to_features(["Foo.java"], skills_dir)
            self.assertEqual(result, {})

    def test_nonexistent_skills_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "does-not-exist"

            result = _map_files_to_features(["Foo.java"], skills_dir)
            self.assertEqual(result, {})

    def test_multiple_changed_files_for_one_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            _write_minimal_skill(skills_dir, "orders",
                                 ["OrderService.java", "OrderRepository.java"])

            result = _map_files_to_features(
                ["src/OrderService.java", "src/OrderRepository.java"], skills_dir
            )
            self.assertIn("orders", result)
            self.assertEqual(len(result["orders"]), 2)


if __name__ == "__main__":
    unittest.main()
