"""
Smoke tests for tools.skill_generator.generate.

Covers:
  - _collect_source_blob with simple class names (sanity)
  - _collect_source_blob with FQN class names — regression for the bug where
    c.split(".")[0] on "com.example.FooService" returned "com" instead of
    "FooService", silently producing empty source blobs.
  - _strip_markdown_fence (used by both generate-ingest and update-ingest)
  - _build_prompt (template substitution)
  - emit_prompts — Stage 3 public API: writes one prompt per domain from
    plan.json + index.json + source files; respects only_domains filter
  - ingest_responses — Stage 3 public API: reads per-domain response files,
    writes SKILL.mds; handles missing/empty responses, existing-file skip,
    force_regen override, only_domains filter, fenced content stripping

All tests use stdlib only (json, tempfile, pathlib, unittest).
"""
import json
import tempfile
import unittest
from pathlib import Path

from tools.skill_generator.generate import (
    _collect_source_blob,
    _build_prompt,
    _strip_markdown_fence,
    _collect_config_pairs,
    _extract_matching_properties_pairs,
    _extract_matching_yaml_pairs,
    _prefix_overlaps,
    emit_prompts,
    ingest_responses,
)


def _make_index(file_path: str, class_name: str) -> dict:
    return {
        "java_classes": [
            {
                "class_name": class_name,
                "file_path": file_path,
            }
        ],
        "xml_signals": [],
        "config_signals": [],
        "sql_signals": [],
        "shell_signals": [],
    }


class TestCollectSourceBlobSimpleNames(unittest.TestCase):
    """Source files are found when the plan uses simple class names."""

    def test_simple_class_name_found(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            src = repo / "src" / "FooService.java"
            src.parent.mkdir(parents=True)
            src.write_text("public class FooService {}", encoding="utf-8")

            domain = {"id": "foo", "classes": ["FooService"]}
            index = _make_index("src/FooService.java", "FooService")
            blob = _collect_source_blob(domain, repo, index)

            self.assertIn("FooService", blob)
            self.assertIn("--- FILE:", blob)

    def test_missing_class_yields_empty_blob(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            domain = {"id": "foo", "classes": ["NotPresent"]}
            index = _make_index("src/FooService.java", "FooService")
            blob = _collect_source_blob(domain, repo, index)
            self.assertEqual(blob.strip(), "")


class TestCollectSourceBlobFQNClassNames(unittest.TestCase):
    """Regression: plan responses sometimes contain FQN class names like
    'com.example.FooService'. split('.')[0] returned 'com' (wrong); the fix
    uses split('.')[-1] which correctly returns 'FooService'."""

    def test_fqn_class_name_found(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            src = repo / "src" / "FooService.java"
            src.parent.mkdir(parents=True)
            src.write_text("public class FooService {}", encoding="utf-8")

            domain = {"id": "foo", "classes": ["com.example.FooService"]}
            index = _make_index("src/FooService.java", "FooService")
            blob = _collect_source_blob(domain, repo, index)

            self.assertIn("FooService", blob,
                          "FQN 'com.example.FooService' should resolve to class_name 'FooService'")
            self.assertIn("--- FILE:", blob)

    def test_deeply_nested_fqn(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            src = repo / "src" / "OrderProcessor.java"
            src.parent.mkdir(parents=True)
            src.write_text("public class OrderProcessor {}", encoding="utf-8")

            domain = {
                "id": "order",
                "classes": ["com.acme.payments.batch.OrderProcessor"],
            }
            index = _make_index("src/OrderProcessor.java", "OrderProcessor")
            blob = _collect_source_blob(domain, repo, index)

            self.assertIn("OrderProcessor", blob)

    def test_mixed_fqn_and_simple_names(self):
        """A plan with some FQNs and some simple names should find all files."""
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "src").mkdir()
            (repo / "src" / "Alpha.java").write_text("class Alpha {}", encoding="utf-8")
            (repo / "src" / "Beta.java").write_text("class Beta {}", encoding="utf-8")

            domain = {
                "id": "mix",
                "classes": ["com.example.Alpha", "Beta"],
            }
            index = {
                "java_classes": [
                    {"class_name": "Alpha", "file_path": "src/Alpha.java"},
                    {"class_name": "Beta", "file_path": "src/Beta.java"},
                ],
                "xml_signals": [],
                "config_signals": [],
                "sql_signals": [],
                "shell_signals": [],
            }
            blob = _collect_source_blob(domain, repo, index)
            self.assertIn("Alpha", blob)
            self.assertIn("Beta", blob)


class TestStripMarkdownFence(unittest.TestCase):
    def test_no_fence(self):
        self.assertEqual(_strip_markdown_fence("hello"), "hello")

    def test_fenced_markdown(self):
        text = "```markdown\n---\nskill: foo\n---\n```"
        result = _strip_markdown_fence(text)
        self.assertNotIn("```", result)
        self.assertIn("skill: foo", result)

    def test_plain_backtick_fence(self):
        text = "```\ncontent here\n```"
        result = _strip_markdown_fence(text)
        self.assertEqual(result.strip(), "content here")

    def test_no_trailing_fence(self):
        text = "```\ncontent here"
        result = _strip_markdown_fence(text)
        self.assertIn("content here", result)


class TestBuildPrompt(unittest.TestCase):
    def test_replacements_applied(self):
        domain = {
            "id": "file-delivery",
            "name": "File Delivery",
            "description": "Handles file transfers.",
        }
        prompt = _build_prompt(domain, "some source code here")
        self.assertIn("file-delivery", prompt)
        self.assertIn("File Delivery", prompt)
        self.assertIn("some source code here", prompt)
        self.assertNotIn("{DOMAIN_ID}", prompt)
        self.assertNotIn("{DOMAIN_NAME}", prompt)
        self.assertNotIn("{SOURCE_BLOB}", prompt)

    def test_source_truncated_when_too_long(self):
        domain = {"id": "big", "name": "Big", "description": ""}
        big_source = "x" * 30_000
        prompt = _build_prompt(domain, big_source)
        self.assertIn("truncated", prompt)


# ─────────────────────────────────────────────────────────────────────────────
# Stage-3 config value collection — regression for the gap where domains had
# `configKeys` in the plan but the generate prompt never actually read those
# values. (Codex's High #4 / release-readiness section 1.)
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractMatchingPropertiesPairs(unittest.TestCase):
    def test_matching_key_kept(self):
        text = (
            "app.file-delivery.max-size-mb=100\n"
            "spring.datasource.url=jdbc:postgresql://localhost/foo\n"
        )
        out = _extract_matching_properties_pairs(text, ["app.file-delivery"])
        self.assertEqual(out, ["app.file-delivery.max-size-mb=100"])

    def test_non_matching_key_dropped(self):
        text = "unrelated.something=value\n"
        out = _extract_matching_properties_pairs(text, ["app.file-delivery"])
        self.assertEqual(out, [])

    def test_exact_match_kept(self):
        text = "datasource=primary\n"
        out = _extract_matching_properties_pairs(text, ["datasource"])
        self.assertEqual(out, ["datasource=primary"])

    def test_comments_and_blanks_ignored(self):
        text = (
            "# this is a comment\n"
            "\n"
            "! also a comment\n"
            "app.x.y=42\n"
        )
        out = _extract_matching_properties_pairs(text, ["app.x"])
        self.assertEqual(out, ["app.x.y=42"])

    def test_colon_separator_supported(self):
        text = "app.x.y: hello\n"
        out = _extract_matching_properties_pairs(text, ["app.x"])
        self.assertEqual(out, ["app.x.y: hello"])

    def test_value_with_url_keeps_first_separator(self):
        # The URL value contains both : and = and // — we must split on the
        # FIRST separator so the value isn't truncated.
        text = "spring.datasource.url=jdbc:postgresql://host:5432/db\n"
        out = _extract_matching_properties_pairs(text, ["spring.datasource"])
        self.assertEqual(out, ["spring.datasource.url=jdbc:postgresql://host:5432/db"])


class TestExtractMatchingYamlPairs(unittest.TestCase):
    def test_nested_leaf_emitted_with_dotted_path(self):
        text = (
            "app:\n"
            "  file-delivery:\n"
            "    max-size-mb: 100\n"
            "    allowed-types: image/png\n"
        )
        out = _extract_matching_yaml_pairs(text, ["app.file-delivery"])
        self.assertIn("app.file-delivery.max-size-mb: 100", out)
        self.assertIn("app.file-delivery.allowed-types: image/png", out)

    def test_section_headers_without_values_not_emitted(self):
        text = (
            "app:\n"
            "  file-delivery:\n"
            "    max-size-mb: 100\n"
        )
        out = _extract_matching_yaml_pairs(text, ["app"])
        # `app:` and `file-delivery:` are section headers with no inline value
        self.assertNotIn("app: ", "\n".join(out))
        self.assertNotIn("app.file-delivery: ", "\n".join(out))
        self.assertIn("app.file-delivery.max-size-mb: 100", out)

    def test_unrelated_sections_dropped(self):
        text = (
            "app:\n"
            "  file-delivery:\n"
            "    max-size-mb: 100\n"
            "logging:\n"
            "  level: INFO\n"
        )
        out = _extract_matching_yaml_pairs(text, ["app"])
        joined = "\n".join(out)
        self.assertIn("app.file-delivery.max-size-mb: 100", out)
        self.assertNotIn("logging", joined)

    def test_comments_ignored(self):
        text = (
            "# top comment\n"
            "app:\n"
            "  # inner comment\n"
            "  x: 1\n"
        )
        out = _extract_matching_yaml_pairs(text, ["app"])
        self.assertEqual(out, ["app.x: 1"])

    def test_value_with_colons_preserved(self):
        text = (
            "spring:\n"
            "  datasource:\n"
            "    url: jdbc:postgresql://host:5432/db\n"
        )
        out = _extract_matching_yaml_pairs(text, ["spring.datasource"])
        self.assertEqual(out, ["spring.datasource.url: jdbc:postgresql://host:5432/db"])


class TestPrefixOverlaps(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(_prefix_overlaps("app.file-delivery", ["app.file-delivery"]))

    def test_file_more_specific_than_plan(self):
        # Plan said 'app'; the file has 'app.file-delivery' — match.
        self.assertTrue(_prefix_overlaps("app.file-delivery", ["app"]))

    def test_plan_more_specific_than_file(self):
        # Plan said 'spring.datasource'; the file only has 'spring' — match.
        self.assertTrue(_prefix_overlaps("spring", ["spring.datasource"]))

    def test_unrelated_no_overlap(self):
        self.assertFalse(_prefix_overlaps("logging", ["app.file-delivery"]))


class TestCollectConfigPairs(unittest.TestCase):
    def _make_config_index(self, files):
        """files: list of (file_path, config_type, [key_prefixes])."""
        return {
            "java_classes": [],
            "xml_signals": [],
            "config_signals": [
                {"file_path": fp, "config_type": ct, "key_prefixes": kps}
                for (fp, ct, kps) in files
            ],
            "sql_signals": [],
            "shell_signals": [],
        }

    def test_no_config_keys_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            domain = {"id": "x", "configKeys": []}
            out = _collect_config_pairs(domain, repo, self._make_config_index([]))
            self.assertEqual(out, "")

    def test_wildcard_prefix_is_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "src" / "main" / "resources").mkdir(parents=True)
            cfg = repo / "src" / "main" / "resources" / "application.properties"
            cfg.write_text("app.file-delivery.max-size-mb=100\n", encoding="utf-8")
            index = self._make_config_index([
                ("src/main/resources/application.properties", "properties",
                 ["app.file-delivery"])
            ])
            domain = {"id": "fd", "configKeys": ["app.file-delivery.*"]}
            out = _collect_config_pairs(domain, repo, index)
            self.assertIn("--- CONFIG: src/main/resources/application.properties ---", out)
            self.assertIn("app.file-delivery.max-size-mb=100", out)

    def test_yaml_pairs_picked_up(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            cfg = repo / "application.yml"
            cfg.write_text(
                "app:\n  file-delivery:\n    max-size-mb: 100\n",
                encoding="utf-8",
            )
            index = self._make_config_index([
                ("application.yml", "yaml", ["app", "app.file-delivery"])
            ])
            domain = {"id": "fd", "configKeys": ["app.file-delivery"]}
            out = _collect_config_pairs(domain, repo, index)
            self.assertIn("app.file-delivery.max-size-mb: 100", out)

    def test_irrelevant_files_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            keep = repo / "keep.properties"
            keep.write_text("app.x.y=1\n", encoding="utf-8")
            skip = repo / "skip.properties"
            skip.write_text("unrelated.z=99\n", encoding="utf-8")
            index = self._make_config_index([
                ("keep.properties", "properties", ["app", "app.x"]),
                ("skip.properties", "properties", ["unrelated"]),
            ])
            domain = {"id": "x", "configKeys": ["app"]}
            out = _collect_config_pairs(domain, repo, index)
            self.assertIn("keep.properties", out)
            self.assertNotIn("skip.properties", out)


class TestCollectSourceBlobIncludesConfig(unittest.TestCase):
    """Integration test: _collect_source_blob must surface config pairs
    alongside Java/XML sources so the Stage-3 prompt actually contains them."""

    def test_config_appended_to_source_blob(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "src").mkdir()
            (repo / "src" / "FooService.java").write_text(
                "public class FooService {}", encoding="utf-8"
            )
            (repo / "application.yml").write_text(
                "app:\n  foo:\n    enabled: true\n", encoding="utf-8"
            )
            domain = {
                "id": "foo",
                "classes": ["FooService"],
                "configKeys": ["app.foo"],
            }
            index = {
                "java_classes": [
                    {"class_name": "FooService", "file_path": "src/FooService.java"}
                ],
                "xml_signals": [],
                "config_signals": [
                    {"file_path": "application.yml", "config_type": "yaml",
                     "key_prefixes": ["app", "app.foo"]}
                ],
                "sql_signals": [],
                "shell_signals": [],
            }
            blob = _collect_source_blob(domain, repo, index)
            self.assertIn("FooService", blob)
            self.assertIn("--- CONFIG: application.yml ---", blob)
            self.assertIn("app.foo.enabled: true", blob)


# ─────────────────────────────────────────────────────────────────────────────
# Public API: emit_prompts and ingest_responses
# ─────────────────────────────────────────────────────────────────────────────

_MINIMAL_PLAN = {
    "projectType": "REST API",
    "framework": "Spring Boot",
    "buildSystem": "Maven",
    "javaVersion": "17",
    "warnings": [],
    "domains": [
        {
            "id": "file-delivery",
            "name": "File Delivery",
            "description": "Handles file transfers",
            "classes": ["FileDeliveryService"],
            "xmlSources": [],
            "sqlSources": [],
            "shellSources": [],
            "configKeys": [],
        }
    ],
}

_MINIMAL_SKILL_MD = """\
---
skill: File Delivery
domain: file-delivery
version: 1
project_type: REST API
framework: Spring Boot
java_version: 17
legacy: false
status: active
flags: none
related_skills: none
generated_by: skill_generator.agent
last_updated: 2026-11-12
---

# File Delivery

## Purpose
Handles file transfers.

## Entry Points
- REST: GET /api/files → FileDeliveryController.get()

## Business Logic

### Core Flow
1. Receive — FileDeliveryController.get()
2. Process — FileDeliveryService.deliver()

### Validation Rules
- Non-null — FileDeliveryService.validate()

### Business Rules
- Returns 200 — FileDeliveryService.deliver()

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| FileDeliveryService.java | Service | core logic |

## Data Flow
GET /api/files → FileDeliveryService.deliver()

## Database & Storage
- Tables: file_delivery

## External Dependencies
none found

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| RuntimeException | failure | 500 |

## Edge Cases
- Null handled — FileDeliveryService.validate()

## Legacy Notes
none found

## Related Skills
none found

## AI Agent Instructions
1. Always validate — FileDeliveryService.validate()
"""


def _write_plan(td: str, plan: dict) -> Path:
    p = Path(td) / "plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    return p


def _write_index(repo: Path, classes: list) -> Path:
    idx = {
        "java_classes": classes,
        "xml_signals": [],
        "config_signals": [],
        "sql_signals": [],
        "shell_signals": [],
    }
    index_path = repo / ".skill-gen" / ".index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(idx), encoding="utf-8")
    return index_path


def _write_java(repo: Path, rel: str, class_name: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"public class {class_name} {{ void work() {{}} }}", encoding="utf-8")


class TestEmitPrompts(unittest.TestCase):
    def _setup(self, td: str):
        """Return (plan_path, repo, index_path) with one domain."""
        repo = Path(td) / "repo"
        repo.mkdir()
        _write_java(repo, "src/FileDeliveryService.java", "FileDeliveryService")
        index_path = _write_index(repo, [
            {"class_name": "FileDeliveryService", "file_path": "src/FileDeliveryService.java"},
        ])
        plan_path = _write_plan(td, _MINIMAL_PLAN)
        return plan_path, repo, index_path

    def test_prompt_written_per_domain(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path, repo, index_path = self._setup(td)
            prompts_dir = Path(td) / "prompts"
            result = emit_prompts(plan_path, repo, index_path=index_path,
                                  prompts_dir=prompts_dir)
            self.assertEqual(len(result["written"]), 1)
            self.assertTrue((prompts_dir / "file-delivery.md").exists())

    def test_prompt_contains_domain_name_and_id(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path, repo, index_path = self._setup(td)
            prompts_dir = Path(td) / "prompts"
            emit_prompts(plan_path, repo, index_path=index_path, prompts_dir=prompts_dir)
            text = (prompts_dir / "file-delivery.md").read_text(encoding="utf-8")
            self.assertIn("file-delivery", text)
            self.assertIn("File Delivery", text)

    def test_prompt_contains_source_code(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path, repo, index_path = self._setup(td)
            prompts_dir = Path(td) / "prompts"
            emit_prompts(plan_path, repo, index_path=index_path, prompts_dir=prompts_dir)
            text = (prompts_dir / "file-delivery.md").read_text(encoding="utf-8")
            self.assertIn("FileDeliveryService", text)

    def test_domain_with_no_source_in_failed(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path, repo, index_path = self._setup(td)
            # Overwrite plan with a domain whose class has no matching index entry
            plan = dict(_MINIMAL_PLAN)
            plan["domains"] = [dict(_MINIMAL_PLAN["domains"][0],
                                    classes=["GhostClass"])]
            plan_path = _write_plan(td, plan)
            prompts_dir = Path(td) / "prompts"
            result = emit_prompts(plan_path, repo, index_path=index_path,
                                  prompts_dir=prompts_dir)
            self.assertEqual(result["written"], [])
            self.assertTrue(any(f["domain"] == "file-delivery"
                                for f in result["failed"]))

    def test_only_domains_skips_other_domains(self):
        with tempfile.TemporaryDirectory() as td:
            # Plan with two domains, only one has source
            _write_java(Path(td) / "repo" / "src2",
                        "InvoiceService.java", "InvoiceService")
            repo = Path(td) / "repo"
            repo.mkdir(exist_ok=True)
            _write_java(repo, "src/FileDeliveryService.java", "FileDeliveryService")
            _write_java(repo, "src/InvoiceService.java", "InvoiceService")
            index_path = _write_index(repo, [
                {"class_name": "FileDeliveryService",
                 "file_path": "src/FileDeliveryService.java"},
                {"class_name": "InvoiceService",
                 "file_path": "src/InvoiceService.java"},
            ])
            two_domain_plan = dict(_MINIMAL_PLAN)
            two_domain_plan["domains"] = [
                _MINIMAL_PLAN["domains"][0],
                {"id": "invoice-compare", "name": "Invoice Compare",
                 "description": "", "classes": ["InvoiceService"],
                 "xmlSources": [], "sqlSources": [], "shellSources": [],
                 "configKeys": []},
            ]
            plan_path = _write_plan(td, two_domain_plan)
            prompts_dir = Path(td) / "prompts"
            result = emit_prompts(plan_path, repo, index_path=index_path,
                                  prompts_dir=prompts_dir,
                                  only_domains=["file-delivery"])
            written_names = [Path(p).stem for p in result["written"]]
            self.assertIn("file-delivery", written_names)
            self.assertNotIn("invoice-compare", written_names)

    def test_result_has_written_skipped_failed_keys(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path, repo, index_path = self._setup(td)
            result = emit_prompts(plan_path, repo, index_path=index_path)
            for key in ("written", "skipped", "failed"):
                self.assertIn(key, result)


class TestIngestResponses(unittest.TestCase):
    def _setup(self, td: str):
        """Return (plan_path, repo, responses_dir, output_dir)."""
        repo = Path(td) / "repo"
        repo.mkdir()
        plan_path = _write_plan(td, _MINIMAL_PLAN)
        responses_dir = Path(td) / "responses"
        responses_dir.mkdir()
        output_dir = Path(td) / "output"
        return plan_path, repo, responses_dir, output_dir

    def test_skill_md_written_on_happy_path(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path, repo, responses_dir, output_dir = self._setup(td)
            (responses_dir / "file-delivery.md").write_text(
                _MINIMAL_SKILL_MD, encoding="utf-8"
            )
            result = ingest_responses(
                plan_path, repo,
                responses_dir=responses_dir,
                output_dir=output_dir,
                validate_schema=False,
            )
            self.assertEqual(len(result["written"]), 1)
            self.assertTrue((output_dir / "file-delivery" / "SKILL.md").exists())

    def test_missing_response_in_failed(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path, repo, responses_dir, output_dir = self._setup(td)
            result = ingest_responses(
                plan_path, repo,
                responses_dir=responses_dir,
                output_dir=output_dir,
                validate_schema=False,
            )
            self.assertEqual(result["written"], [])
            self.assertTrue(any(f["domain"] == "file-delivery"
                                for f in result["failed"]))

    def test_empty_response_in_failed(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path, repo, responses_dir, output_dir = self._setup(td)
            (responses_dir / "file-delivery.md").write_text("", encoding="utf-8")
            result = ingest_responses(
                plan_path, repo,
                responses_dir=responses_dir,
                output_dir=output_dir,
                validate_schema=False,
            )
            failed_ids = [f["domain"] for f in result["failed"]]
            self.assertIn("file-delivery", failed_ids)

    def test_existing_skill_skipped_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path, repo, responses_dir, output_dir = self._setup(td)
            # Pre-create a SKILL.md so the ingest would need --force to overwrite
            skill_path = output_dir / "file-delivery" / "SKILL.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text("existing content", encoding="utf-8")
            (responses_dir / "file-delivery.md").write_text(
                _MINIMAL_SKILL_MD, encoding="utf-8"
            )
            result = ingest_responses(
                plan_path, repo,
                responses_dir=responses_dir,
                output_dir=output_dir,
                validate_schema=False,
                force_regen=False,
            )
            self.assertEqual(result["written"], [])
            self.assertIn("file-delivery", result["skipped"])
            # Original content preserved
            self.assertEqual(skill_path.read_text(encoding="utf-8"), "existing content")

    def test_force_regen_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path, repo, responses_dir, output_dir = self._setup(td)
            skill_path = output_dir / "file-delivery" / "SKILL.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text("old content", encoding="utf-8")
            (responses_dir / "file-delivery.md").write_text(
                _MINIMAL_SKILL_MD, encoding="utf-8"
            )
            result = ingest_responses(
                plan_path, repo,
                responses_dir=responses_dir,
                output_dir=output_dir,
                validate_schema=False,
                force_regen=True,
            )
            self.assertEqual(len(result["written"]), 1)
            self.assertNotEqual(skill_path.read_text(encoding="utf-8"), "old content")

    def test_only_domains_processes_named_domain_only(self):
        with tempfile.TemporaryDirectory() as td:
            two_domain_plan = dict(_MINIMAL_PLAN)
            two_domain_plan["domains"] = [
                _MINIMAL_PLAN["domains"][0],
                {"id": "invoice-compare", "name": "Invoice Compare",
                 "description": "", "classes": [],
                 "xmlSources": [], "sqlSources": [], "shellSources": [],
                 "configKeys": []},
            ]
            plan_path = _write_plan(td, two_domain_plan)
            repo = Path(td) / "repo"
            repo.mkdir()
            responses_dir = Path(td) / "responses"
            responses_dir.mkdir()
            output_dir = Path(td) / "output"
            (responses_dir / "file-delivery.md").write_text(
                _MINIMAL_SKILL_MD, encoding="utf-8"
            )
            (responses_dir / "invoice-compare.md").write_text(
                _MINIMAL_SKILL_MD.replace("file-delivery", "invoice-compare")
                .replace("File Delivery", "Invoice Compare"),
                encoding="utf-8",
            )
            result = ingest_responses(
                plan_path, repo,
                responses_dir=responses_dir,
                output_dir=output_dir,
                validate_schema=False,
                only_domains=["file-delivery"],
            )
            written_names = [Path(p).parent.name for p in result["written"]]
            self.assertIn("file-delivery", written_names)
            self.assertNotIn("invoice-compare", written_names)

    def test_fenced_response_content_stripped(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path, repo, responses_dir, output_dir = self._setup(td)
            fenced = "```\n" + _MINIMAL_SKILL_MD + "\n```"
            (responses_dir / "file-delivery.md").write_text(fenced, encoding="utf-8")
            result = ingest_responses(
                plan_path, repo,
                responses_dir=responses_dir,
                output_dir=output_dir,
                validate_schema=False,
            )
            self.assertEqual(len(result["written"]), 1)
            written = (output_dir / "file-delivery" / "SKILL.md").read_text(
                encoding="utf-8"
            )
            self.assertFalse(written.strip().startswith("```"))

    def test_result_has_written_skipped_failed_keys(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path, repo, responses_dir, output_dir = self._setup(td)
            result = ingest_responses(
                plan_path, repo,
                responses_dir=responses_dir,
                output_dir=output_dir,
                validate_schema=False,
            )
            for key in ("written", "skipped", "failed"):
                self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()
