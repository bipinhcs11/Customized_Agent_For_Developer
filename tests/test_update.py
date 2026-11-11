"""
Smoke tests for tools.skill_generator.update — pure-function coverage.

Covers:
  - _bump_version — extracts current version and returns (old, new) pair
  - _domain_from_skill — reconstructs a minimal domain dict from SKILL.md text
  - _map_files_to_features — maps changed files to feature ids via SKILL.md content

All tests use stdlib only (tempfile, pathlib, unittest).
"""
import tempfile
import unittest
from pathlib import Path

from tools.skill_generator.update import (
    _bump_version,
    _domain_from_skill,
    _map_files_to_features,
)


MINIMAL_SKILL_MD = """\
---
skill: file-delivery
domain: File Delivery
version: 3
project_type: REST API
framework: Spring Boot
java_version: 17
legacy: false
status: active
flags: []
related_skills: []
generated_by: skill-gen 0.2.0
last_updated: 2024-01-01
---

## Purpose
Handles file transfer.

## Entry Points
FileDeliveryController.deliver() — POST /api/files

## Business Logic

### Core Flow
FileDeliveryService.process() — main flow

### Validation Rules
none found

### Business Rules
none found

## Key Classes & Files
| Class | File |
|---|---|
| FileDeliveryService | FileDeliveryService.java |
| FileDeliveryController | FileDeliveryController.java |

## Data Flow
none found

## Database & Storage
none found

## External Dependencies
none found

## Error Handling
none found

## Edge Cases
none found

## Legacy Notes
none found

## Related Skills
none found

## AI Agent Instructions
none found
"""


class TestBumpVersion(unittest.TestCase):
    def test_bumps_integer_version(self):
        old, new = _bump_version(MINIMAL_SKILL_MD)
        self.assertEqual(old, 3)
        self.assertEqual(new, 4)

    def test_version_1_when_missing(self):
        """When no version: field is present, treat as 1 and bump to 2."""
        md = "---\nskill: foo\n---\n## Purpose\nnone found\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_version_zero(self):
        md = MINIMAL_SKILL_MD.replace("version: 3", "version: 0")
        old, new = _bump_version(md)
        self.assertEqual(old, 0)
        self.assertEqual(new, 1)


class TestDomainFromSkill(unittest.TestCase):
    def test_extracts_java_classes(self):
        domain = _domain_from_skill(MINIMAL_SKILL_MD, "file-delivery")
        self.assertIn("FileDeliveryService", domain["classes"])
        self.assertIn("FileDeliveryController", domain["classes"])

    def test_id_and_name_set(self):
        domain = _domain_from_skill(MINIMAL_SKILL_MD, "file-delivery")
        self.assertEqual(domain["id"], "file-delivery")
        self.assertEqual(domain["name"], "file-delivery")

    def test_no_java_files_returns_empty_classes(self):
        domain = _domain_from_skill("no java refs here", "empty-feature")
        self.assertEqual(domain["classes"], [])

    def test_xml_sources_captured(self):
        md = MINIMAL_SKILL_MD + "\nSee applicationContext.xml for bean wiring.\n"
        domain = _domain_from_skill(md, "file-delivery")
        xml_fps = [s.split(":")[0].strip() for s in domain.get("xmlSources", [])]
        self.assertIn("applicationContext.xml", xml_fps)


class TestMapFilesToFeatures(unittest.TestCase):
    def test_maps_changed_file_to_feature(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)
            fd_dir = skills_dir / "file-delivery"
            fd_dir.mkdir()
            (fd_dir / "SKILL.md").write_text(MINIMAL_SKILL_MD)

            result = _map_files_to_features(
                ["src/main/java/FileDeliveryService.java"],
                skills_dir,
            )
            self.assertIn("file-delivery", result)
            self.assertIn("src/main/java/FileDeliveryService.java",
                          result["file-delivery"])

    def test_no_match_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)
            fd_dir = skills_dir / "file-delivery"
            fd_dir.mkdir()
            (fd_dir / "SKILL.md").write_text(MINIMAL_SKILL_MD)

            result = _map_files_to_features(
                ["src/main/java/UnrelatedClass.java"],
                skills_dir,
            )
            self.assertEqual(result, {})

    def test_nonexistent_skills_dir_returns_empty(self):
        result = _map_files_to_features(
            ["AnyFile.java"],
            Path("/nonexistent/skills"),
        )
        self.assertEqual(result, {})

    def test_empty_changed_files_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)
            (skills_dir / "some-feature").mkdir()
            (skills_dir / "some-feature" / "SKILL.md").write_text(MINIMAL_SKILL_MD)
            result = _map_files_to_features([], skills_dir)
            self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
