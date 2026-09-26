"""
Smoke tests for tools.skill_generator.update (pure functions only).

Covers the three functions that have no subprocess/git dependency:
  - _bump_version — extracts the current version and computes the next one
  - _domain_from_skill — reconstructs a minimal domain dict from a SKILL.md
  - _map_files_to_features — maps a list of changed file paths to feature ids
      by scanning existing SKILL.md files for references

Excludes emit_prompts / ingest_responses because they shell out to git and
write/read the filesystem in ways that require heavier fixture scaffolding.

All tests use stdlib only (tempfile, pathlib, textwrap, unittest).
"""
import tempfile
import textwrap
import unittest
from pathlib import Path

from tools.skill_generator.update import (
    _bump_version,
    _domain_from_skill,
    _map_files_to_features,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _skill_with_version(version: int) -> str:
    return textwrap.dedent(f"""\
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
        last_updated: 2026-05-01
        ---

        ## Purpose
        Handles file transfers.

        ## Entry Points
        - REST: POST /api/files → FileDeliveryController.upload()

        ## Business Logic

        ### Core Flow
        1. Receive — FileDeliveryController.upload()
        2. Persist — FileDeliveryService.save()

        ### Validation Rules
        - Non-null check — FileDeliveryService.validate()

        ### Business Rules
        - Status must be PENDING — FileDeliveryService.validate()

        ## Key Classes & Files
        | File | Type | Role |
        |------|------|------|
        | FileDeliveryService.java | Service | core logic |
        | FileDeliveryController.java | Controller | REST entry |
        | FileDeliveryRepository.java | Repository | DB access |

        ## Data Flow
        ```
        POST /api/files
           v
        FileDeliveryController.upload()
        ```

        ## Database & Storage
        - Table: file_delivery

        ## External Dependencies
        none found

        ## Error Handling
        | Exception | Trigger | Handling |
        |-----------|---------|---------|
        | IllegalArgumentException | null input | 400 |

        ## Edge Cases
        - Null file — FileDeliveryService.validate()

        ## Legacy Notes
        none found

        ## Related Skills
        none found

        ## AI Agent Instructions
        1. Always validate — FileDeliveryService.validate()
    """)


def _skill_with_references() -> str:
    """SKILL.md that explicitly mentions several file basenames."""
    return textwrap.dedent("""\
        ---
        skill: Invoice Compare
        domain: invoice-compare
        version: 1
        project_type: REST API
        framework: Spring Boot
        java_version: 17
        legacy: false
        status: active
        flags: none
        related_skills: none
        generated_by: skill_generator.agent
        last_updated: 2026-05-01
        ---

        ## Purpose
        Compares invoices for discrepancies.

        ## Entry Points
        - REST: POST /api/invoices/compare → InvoiceCompareController.compare()

        ## Business Logic

        ### Core Flow
        1. Receive — InvoiceCompareController.compare()
        2. Diff — InvoiceCompareService.compare()

        ### Validation Rules
        - Non-null — InvoiceCompareService.validate()

        ### Business Rules
        - Threshold check — InvoiceCompareService.compare()

        ## Key Classes & Files
        | File | Type | Role |
        |------|------|------|
        | InvoiceCompareService.java | Service | core logic |
        | InvoiceCompareController.java | Controller | REST entry |
        | InvoiceCompareMapper.xml | XML | SQL mapper |
        | invoice_compare.sql | SQL | schema |
        | compare.sh | Shell | batch trigger |

        ## Data Flow
        ```
        POST /api/invoices/compare
           v
        InvoiceCompareService.compare()
        ```

        ## Database & Storage
        - Table: invoice_compare

        ## External Dependencies
        none found

        ## Error Handling
        | Exception | Trigger | Handling |
        |-----------|---------|---------|
        | RuntimeException | mismatch | 500 |

        ## Edge Cases
        - Empty invoice — InvoiceCompareService.validate()

        ## Legacy Notes
        none found

        ## Related Skills
        none found

        ## AI Agent Instructions
        1. Always validate — InvoiceCompareService.validate()
    """)


# ─────────────────────────────────────────────────────────────────────────────
# _bump_version
# ─────────────────────────────────────────────────────────────────────────────

class TestBumpVersion(unittest.TestCase):
    def test_version_1_bumped_to_2(self):
        old, new = _bump_version(_skill_with_version(1))
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_version_5_bumped_to_6(self):
        old, new = _bump_version(_skill_with_version(5))
        self.assertEqual(old, 5)
        self.assertEqual(new, 6)

    def test_version_0_bumped_to_1(self):
        old, new = _bump_version(_skill_with_version(0))
        self.assertEqual(old, 0)
        self.assertEqual(new, 1)

    def test_version_10_bumped_to_11(self):
        old, new = _bump_version(_skill_with_version(10))
        self.assertEqual(old, 10)
        self.assertEqual(new, 11)

    def test_no_version_field_falls_back_to_1_and_2(self):
        md = "---\nskill: NoVersion\n---\n\n## Purpose\nnone found\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_new_version_is_always_old_plus_one(self):
        for v in (0, 1, 3, 42, 99):
            with self.subTest(v=v):
                old, new = _bump_version(_skill_with_version(v))
                self.assertEqual(new, old + 1)


# ─────────────────────────────────────────────────────────────────────────────
# _domain_from_skill
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainFromSkill(unittest.TestCase):
    def setUp(self):
        self.domain = _domain_from_skill(_skill_with_references(), "invoice-compare")

    def test_feature_id_set_correctly(self):
        self.assertEqual(self.domain["id"], "invoice-compare")
        self.assertEqual(self.domain["name"], "invoice-compare")

    def test_java_classes_extracted(self):
        # The skill mentions InvoiceCompareService.java and InvoiceCompareController.java
        classes = self.domain["classes"]
        self.assertIn("InvoiceCompareService", classes)
        self.assertIn("InvoiceCompareController", classes)

    def test_xml_sources_extracted(self):
        xml = self.domain["xmlSources"]
        xml_files = [x.split(":")[0].strip() for x in xml]
        self.assertIn("InvoiceCompareMapper.xml", xml_files)

    def test_sql_sources_extracted(self):
        sql = self.domain["sqlSources"]
        sql_files = [s.split(":")[0].strip() for s in sql]
        self.assertIn("invoice_compare.sql", sql_files)

    def test_shell_sources_extracted(self):
        sh = self.domain["shellSources"]
        sh_files = [s.split(":")[0].strip() for s in sh]
        self.assertIn("compare.sh", sh_files)

    def test_empty_skill_produces_empty_lists(self):
        minimal = "---\nskill: Empty\ndomain: empty\n---\n\n## Purpose\nnone found\n"
        d = _domain_from_skill(minimal, "empty")
        self.assertEqual(d["id"], "empty")
        self.assertEqual(d["classes"], [])

    def test_description_is_empty_string(self):
        self.assertEqual(self.domain["description"], "")

    def test_lowercase_java_names_not_extracted(self):
        # Class names must start with uppercase; helpers / config files should not be extracted
        md = "FileDeliveryService.java and some-lowercase.java are referenced."
        d = _domain_from_skill(md, "test")
        classes = d["classes"]
        self.assertIn("FileDeliveryService", classes)
        # 'lowercase' starts with a lowercase letter — must not appear
        self.assertNotIn("lowercase", classes)


# ─────────────────────────────────────────────────────────────────────────────
# _map_files_to_features
# ─────────────────────────────────────────────────────────────────────────────

class TestMapFilesToFeatures(unittest.TestCase):
    def _make_skills_dir(self, td: str) -> Path:
        """Create a minimal skills dir with two features."""
        skills_dir = Path(td) / "skills"
        (skills_dir / "file-delivery").mkdir(parents=True)
        (skills_dir / "invoice-compare").mkdir(parents=True)
        (skills_dir / "file-delivery" / "SKILL.md").write_text(
            _skill_with_version(1), encoding="utf-8"
        )
        (skills_dir / "invoice-compare" / "SKILL.md").write_text(
            _skill_with_references(), encoding="utf-8"
        )
        return skills_dir

    def test_nonexistent_skills_dir_returns_empty(self):
        result = _map_files_to_features(
            ["src/SomeService.java"],
            Path("/nonexistent_skills_dir_abc"),
        )
        self.assertEqual(result, {})

    def test_known_java_file_maps_to_correct_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._make_skills_dir(td)
            result = _map_files_to_features(
                ["src/FileDeliveryService.java"], skills_dir
            )
            self.assertIn("file-delivery", result)
            self.assertIn("src/FileDeliveryService.java", result["file-delivery"])

    def test_known_xml_file_maps_to_correct_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._make_skills_dir(td)
            result = _map_files_to_features(
                ["src/InvoiceCompareMapper.xml"], skills_dir
            )
            self.assertIn("invoice-compare", result)

    def test_unknown_file_is_not_in_result(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._make_skills_dir(td)
            result = _map_files_to_features(
                ["src/BrandNewFeature.java"], skills_dir
            )
            self.assertNotIn("file-delivery", result)
            self.assertNotIn("invoice-compare", result)

    def test_empty_changed_list_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._make_skills_dir(td)
            result = _map_files_to_features([], skills_dir)
            self.assertEqual(result, {})

    def test_multiple_files_in_same_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._make_skills_dir(td)
            result = _map_files_to_features(
                [
                    "src/FileDeliveryService.java",
                    "src/FileDeliveryController.java",
                ],
                skills_dir,
            )
            self.assertIn("file-delivery", result)
            self.assertEqual(len(result["file-delivery"]), 2)

    def test_files_from_two_features_mapped_independently(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._make_skills_dir(td)
            result = _map_files_to_features(
                [
                    "src/FileDeliveryService.java",
                    "src/InvoiceCompareService.java",
                ],
                skills_dir,
            )
            self.assertIn("file-delivery", result)
            self.assertIn("invoice-compare", result)


if __name__ == "__main__":
    unittest.main()
