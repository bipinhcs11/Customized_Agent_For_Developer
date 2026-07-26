"""
Smoke tests for tools.skill_generator.update — pure-function tier.

Covers:
  - _bump_version: version extraction and increment logic
  - _domain_from_skill: regex extraction of classes/files from an existing SKILL.md
  - _map_files_to_features: changed-file -> feature mapping via SKILL.md basenames
  - ingest_responses: version bump, date stamp, write, and failure paths

All tests are hermetic (stdlib + tempfile only). No git commands are issued —
emit_prompts is exercised only via ingest_responses, which tests the full
read-transform-write cycle without the subprocess layer.
"""
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


class TestBumpVersion(unittest.TestCase):
    def test_bumps_existing_version(self):
        md = "---\nversion: 3\nstatus: active\n---\n## Purpose\nnone found\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 3)
        self.assertEqual(new, 4)

    def test_defaults_to_one_when_no_version_field(self):
        md = "---\nstatus: active\n---\n## Purpose\nnone found\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_version_one(self):
        old, new = _bump_version("---\nversion: 1\n---\n")
        self.assertEqual(old, 1)
        self.assertEqual(new, 2)

    def test_large_version(self):
        old, new = _bump_version("---\nversion: 42\n---\n")
        self.assertEqual(old, 42)
        self.assertEqual(new, 43)

    def test_body_prose_version_not_counted(self):
        # "version: 99" inside the body should NOT be matched; the frontmatter
        # field "version: 5" comes first and the regex matches the first ^version:
        # line, which is in the frontmatter (body lines start with prose, not the
        # bare word "version:").
        md = "---\nversion: 5\n---\nThe system runs version: 99 of the protocol.\n"
        old, new = _bump_version(md)
        self.assertEqual(old, 5)
        self.assertEqual(new, 6)


class TestDomainFromSkill(unittest.TestCase):
    _SKILL = (
        "---\nskill: file-delivery\nversion: 2\n---\n"
        "## Key Classes & Files\n\n"
        "| Class | Role |\n"
        "|---|---|\n"
        "| FileDeliveryService.java | Main service |\n"
        "| FileDeliveryController.java | REST entry point |\n\n"
        "## Database & Storage\n\n"
        "Schema in `file_delivery_schema.sql`. Cleanup via `cleanup.sh`.\n"
        "Spring wiring in `applicationContext.xml`.\n"
    )

    def test_java_classes_extracted(self):
        domain = _domain_from_skill(self._SKILL, "file-delivery")
        self.assertIn("FileDeliveryService", domain["classes"])
        self.assertIn("FileDeliveryController", domain["classes"])

    def test_sql_sources_extracted(self):
        domain = _domain_from_skill(self._SKILL, "file-delivery")
        sql_files = [s.split(":")[0].strip() for s in domain["sqlSources"]]
        self.assertIn("file_delivery_schema.sql", sql_files)

    def test_shell_sources_extracted(self):
        domain = _domain_from_skill(self._SKILL, "file-delivery")
        sh_files = [s.split(":")[0].strip() for s in domain["shellSources"]]
        self.assertIn("cleanup.sh", sh_files)

    def test_xml_sources_extracted(self):
        domain = _domain_from_skill(self._SKILL, "file-delivery")
        xml_files = [s.split(":")[0].strip() for s in domain["xmlSources"]]
        self.assertIn("applicationContext.xml", xml_files)

    def test_feature_id_preserved(self):
        domain = _domain_from_skill(self._SKILL, "file-delivery")
        self.assertEqual(domain["id"], "file-delivery")
        self.assertEqual(domain["name"], "file-delivery")

    def test_empty_skill_returns_empty_lists(self):
        domain = _domain_from_skill("---\nversion: 1\n---\n", "empty-feature")
        self.assertEqual(domain["classes"], [])
        self.assertEqual(domain["xmlSources"], [])
        self.assertEqual(domain["sqlSources"], [])
        self.assertEqual(domain["shellSources"], [])


class TestMapFilesToFeatures(unittest.TestCase):
    def _make_skills_dir(self, tmpdir: str, skills: dict) -> Path:
        skills_dir = Path(tmpdir) / ".github" / "skills"
        for fid, content in skills.items():
            p = skills_dir / fid / "SKILL.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return skills_dir

    def test_changed_file_mapped_to_owning_feature(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._make_skills_dir(td, {
                "file-delivery": "FileDeliveryService.java handles delivery.\n",
            })
            result = _map_files_to_features(
                ["src/main/java/FileDeliveryService.java"], skills_dir
            )
            self.assertIn("file-delivery", result)
            self.assertIn(
                "src/main/java/FileDeliveryService.java",
                result["file-delivery"],
            )

    def test_unmatched_file_absent_from_result(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._make_skills_dir(td, {
                "file-delivery": "FileDeliveryService.java is core.\n",
            })
            result = _map_files_to_features(["src/UnknownClass.java"], skills_dir)
            self.assertNotIn("file-delivery", result)

    def test_empty_changed_list_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._make_skills_dir(td, {
                "file-delivery": "FileDeliveryService.java.\n",
            })
            self.assertEqual(_map_files_to_features([], skills_dir), {})

    def test_nonexistent_skills_dir_returns_empty(self):
        result = _map_files_to_features(
            ["Foo.java"], Path("/tmp/__nonexistent_skills_dir_9f3a__")
        )
        self.assertEqual(result, {})

    def test_file_shared_by_two_features_maps_to_both(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._make_skills_dir(td, {
                "feature-a": "Uses SharedConfig.java for settings.\n",
                "feature-b": "Also reads SharedConfig.java at startup.\n",
            })
            result = _map_files_to_features(["src/SharedConfig.java"], skills_dir)
            self.assertIn("feature-a", result)
            self.assertIn("feature-b", result)

    def test_xml_file_matched(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._make_skills_dir(td, {
                "batch-jobs": "Jobs wired via spring-batch-context.xml.\n",
            })
            result = _map_files_to_features(
                ["src/resources/spring-batch-context.xml"], skills_dir
            )
            self.assertIn("batch-jobs", result)


class TestIngestResponses(unittest.TestCase):
    # Minimal frontmatter that satisfies the version/date substitution.
    # validate_schema=False is used throughout so we don't need a full body.
    _RESPONSE = (
        "---\n"
        "skill: order-management\n"
        "domain: Order Management\n"
        "version: 99\n"
        "project_type: REST API\n"
        "framework: Spring Boot\n"
        "java_version: 17\n"
        "legacy: false\n"
        "status: active\n"
        "flags: []\n"
        "related_skills: []\n"
        "generated_by: skill-gen v0.2\n"
        "last_updated: 2020-01-01\n"
        "---\n\n"
        "## Purpose\n\nnone found\n"
    )

    def _setup(self, tmpdir: str, existing_version: int = 1) -> tuple:
        """Write skills + response fixtures; return (skills_dir, responses_dir, skill_path)."""
        skills_dir = Path(tmpdir) / ".github" / "skills"
        skill_path = skills_dir / "order-management" / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(
            self._RESPONSE.replace("version: 99", f"version: {existing_version}"),
            encoding="utf-8",
        )
        responses_dir = Path(tmpdir) / ".skill-gen" / ".update-responses"
        responses_dir.mkdir(parents=True, exist_ok=True)
        (responses_dir / "order-management.md").write_text(
            self._RESPONSE, encoding="utf-8"
        )
        return skills_dir, responses_dir, skill_path

    def test_version_bumped_to_old_plus_one(self):
        with tempfile.TemporaryDirectory() as td:
            _, responses_dir, skill_path = self._setup(td, existing_version=7)
            ingest_responses(
                Path(td), responses_dir=responses_dir,
                commit=False, validate_schema=False,
            )
            self.assertIn("version: 8", skill_path.read_text(encoding="utf-8"))

    def test_version_in_response_overridden(self):
        # The AI response contains "version: 99" but ingest must force the
        # computed new_ver (old + 1), not whatever the AI wrote.
        with tempfile.TemporaryDirectory() as td:
            _, responses_dir, skill_path = self._setup(td, existing_version=3)
            ingest_responses(
                Path(td), responses_dir=responses_dir,
                commit=False, validate_schema=False,
            )
            content = skill_path.read_text(encoding="utf-8")
            self.assertIn("version: 4", content)
            self.assertNotIn("version: 99", content)

    def test_last_updated_set_to_today(self):
        with tempfile.TemporaryDirectory() as td:
            _, responses_dir, skill_path = self._setup(td)
            ingest_responses(
                Path(td), responses_dir=responses_dir,
                commit=False, validate_schema=False,
            )
            self.assertIn(
                f"last_updated: {date.today().isoformat()}",
                skill_path.read_text(encoding="utf-8"),
            )

    def test_stale_date_in_response_overridden(self):
        # Response has last_updated: 2020-01-01; ingest must stamp today's date.
        with tempfile.TemporaryDirectory() as td:
            _, responses_dir, skill_path = self._setup(td)
            ingest_responses(
                Path(td), responses_dir=responses_dir,
                commit=False, validate_schema=False,
            )
            self.assertNotIn("2020-01-01", skill_path.read_text(encoding="utf-8"))

    def test_skill_path_in_updated_list(self):
        with tempfile.TemporaryDirectory() as td:
            _, responses_dir, skill_path = self._setup(td)
            result = ingest_responses(
                Path(td), responses_dir=responses_dir,
                commit=False, validate_schema=False,
            )
            self.assertIn(str(skill_path), result["updated"])

    def test_empty_response_added_to_failed(self):
        with tempfile.TemporaryDirectory() as td:
            _, responses_dir, _ = self._setup(td)
            (responses_dir / "order-management.md").write_text("   ", encoding="utf-8")
            result = ingest_responses(
                Path(td), responses_dir=responses_dir,
                commit=False, validate_schema=False,
            )
            self.assertEqual(result["updated"], [])
            self.assertTrue(
                any(f["feature"] == "order-management" for f in result["failed"])
            )

    def test_missing_response_via_feature_flag_goes_to_failed(self):
        # When --feature is passed, ingest constructs a specific response path
        # and reports it as failed if the file does not exist.
        with tempfile.TemporaryDirectory() as td:
            skill_path = (
                Path(td) / ".github" / "skills" / "order-management" / "SKILL.md"
            )
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(
                self._RESPONSE.replace("version: 99", "version: 1"), encoding="utf-8"
            )
            responses_dir = Path(td) / ".skill-gen" / ".update-responses"
            responses_dir.mkdir(parents=True, exist_ok=True)
            # No response file written
            result = ingest_responses(
                Path(td), responses_dir=responses_dir,
                feature="order-management", commit=False, validate_schema=False,
            )
            self.assertTrue(
                any(f["feature"] == "order-management" for f in result["failed"])
            )

    def test_no_skills_dir_returns_empty_updated(self):
        with tempfile.TemporaryDirectory() as td:
            result = ingest_responses(Path(td), commit=False, validate_schema=False)
            self.assertEqual(result.get("updated", []), [])

    def test_fenced_response_fence_stripped(self):
        # AI sometimes wraps the SKILL.md in a markdown fence; ingest must
        # strip it so the written file starts with "---\n".
        with tempfile.TemporaryDirectory() as td:
            _, responses_dir, skill_path = self._setup(td)
            inner = self._RESPONSE.replace("version: 99", "version: 1")
            (responses_dir / "order-management.md").write_text(
                f"```markdown\n{inner}\n```", encoding="utf-8"
            )
            result = ingest_responses(
                Path(td), responses_dir=responses_dir,
                commit=False, validate_schema=False,
            )
            self.assertFalse(
                result["failed"],
                f"Fence stripping should succeed; got failures: {result['failed']}",
            )
            written = skill_path.read_text(encoding="utf-8")
            self.assertNotIn("```", written)

    def test_feature_flag_restricts_to_one_feature(self):
        # When --feature is passed only that feature's response is consumed;
        # sibling response files must be ignored.
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / ".github" / "skills"
            responses_dir = Path(td) / ".skill-gen" / ".update-responses"
            responses_dir.mkdir(parents=True, exist_ok=True)
            for fid in ("alpha", "beta"):
                sp = skills_dir / fid / "SKILL.md"
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text(
                    self._RESPONSE.replace("order-management", fid)
                                  .replace("version: 99", "version: 1"),
                    encoding="utf-8",
                )
                (responses_dir / f"{fid}.md").write_text(
                    self._RESPONSE.replace("order-management", fid),
                    encoding="utf-8",
                )
            result = ingest_responses(
                Path(td), responses_dir=responses_dir,
                feature="alpha", commit=False, validate_schema=False,
            )
            updated_names = [Path(p).parent.name for p in result["updated"]]
            self.assertIn("alpha", updated_names)
            self.assertNotIn("beta", updated_names)

    def test_missing_skill_md_reported_as_failed(self):
        # If the skills/ directory exists but has no subdir for the feature,
        # the feature should land in "failed" with reason "skill not found".
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".github" / "skills").mkdir(parents=True)
            responses_dir = Path(td) / ".skill-gen" / ".update-responses"
            responses_dir.mkdir(parents=True)
            (responses_dir / "ghost.md").write_text(self._RESPONSE, encoding="utf-8")
            result = ingest_responses(
                Path(td), responses_dir=responses_dir,
                commit=False, validate_schema=False,
            )
            reasons = [f["reason"] for f in result["failed"]]
            self.assertIn("skill not found", reasons)


class TestResolveSkillsDir(unittest.TestCase):
    def test_github_skills_dir_found(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "myrepo"
            expected = repo / ".github" / "skills"
            expected.mkdir(parents=True)
            self.assertEqual(_resolve_skills_dir(repo), expected)

    def test_plain_skills_dir_found_when_no_github_dir(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "myrepo"
            expected = repo / "skills"
            expected.mkdir(parents=True)
            self.assertEqual(_resolve_skills_dir(repo), expected)

    def test_github_skills_preferred_over_plain_skills(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "myrepo"
            (repo / ".github" / "skills").mkdir(parents=True)
            (repo / "skills").mkdir(parents=True)
            result = _resolve_skills_dir(repo)
            self.assertEqual(result, repo / ".github" / "skills")

    def test_neither_dir_exists_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "no-skills-here"
            repo.mkdir()
            self.assertIsNone(_resolve_skills_dir(repo))


if __name__ == "__main__":
    unittest.main()
