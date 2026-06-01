"""
Tests for tools.skill_generator.validate — the SKILL.md schema validator.

Covers:
  - the happy path on a synthetic valid SKILL.md
  - each individual rule (missing frontmatter, missing field, non-integer
    version, missing section, reordered sections, missing Business Logic
    subsection, Java code block, empty section without "none found",
    citation absent in a populated section)
  - regression: all three hand-authored reference skills in this repo
    (file-delivery, invoice-compare, payment-method-determination) must
    pass with zero errors. They are the documented quality bar and
    breaking that contract should fail tests, not just CI logs.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from tools.skill_generator.validate import (
    validate,
    validate_file,
    REQUIRED_BODY_SECTIONS,
    REQUIRED_FRONTMATTER_FIELDS,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


VALID_SAMPLE = """---
skill: Sample Feature
domain: sample
version: 1
project_type: REST API
framework: Spring Boot
java_version: 17
legacy: false
status: active
flags: none
related_skills: none
generated_by: skill_generator.agent
last_updated: 2026-05-16
---

# Sample Feature

## Purpose
Does something useful for the business.

## Entry Points
- REST: GET /api/sample → SampleController.get()

## Business Logic

### Core Flow
1. Receive request — SampleController.get()
2. Process — SampleService.process()

### Validation Rules
- Input must be non-null — SampleService.validate()

### Business Rules
- Returns 200 on success — SampleService.process()

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| SampleController.java | Controller | REST endpoint |

## Data Flow
```
GET /api/sample
   |
   v
SampleController.get()
```

## Database & Storage
- Tables: sample

## External Dependencies
none found

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| RuntimeException | failure | 500 |

## Edge Cases
- Null input handled — SampleService.validate()

## Legacy Notes
none found

## Related Skills
none found

## AI Agent Instructions
1. Always check input — SampleService.validate()
"""


class TestValidSample(unittest.TestCase):
    def test_valid_sample_passes(self):
        result = validate(VALID_SAMPLE, path="<sample>")
        self.assertTrue(
            result.ok,
            f"expected sample to validate cleanly; got errors: {result.errors}",
        )
        self.assertEqual(result.warnings, [],
                         f"expected no warnings; got: {result.warnings}")


class TestFrontmatter(unittest.TestCase):
    def test_missing_frontmatter_errors(self):
        text = "# Just a heading, no frontmatter\n\n## Purpose\nfoo\n"
        result = validate(text)
        self.assertFalse(result.ok)
        self.assertTrue(any("missing YAML frontmatter" in e for e in result.errors))

    def test_missing_required_field_errors(self):
        # Drop `version` from a valid sample
        broken = VALID_SAMPLE.replace("version: 1\n", "")
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("frontmatter missing required field: version" in e
                            for e in result.errors))

    def test_non_integer_version_errors(self):
        broken = VALID_SAMPLE.replace("version: 1\n", "version: 1.0.0\n")
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("'version' must be an integer" in e for e in result.errors))

    def test_empty_value_errors(self):
        # Codex follow-up: `skill: ` with empty value should error, not pass
        broken = VALID_SAMPLE.replace("skill: Sample Feature\n", "skill: \n")
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("'skill' is empty" in e for e in result.errors))

    def test_all_required_fields_covered(self):
        # Sanity: every field documented as required is in the REQUIRED list
        for fld in ("skill", "domain", "version", "project_type", "framework",
                    "java_version", "legacy", "status", "flags",
                    "related_skills", "generated_by", "last_updated"):
            self.assertIn(fld, REQUIRED_FRONTMATTER_FIELDS)


class TestBodySections(unittest.TestCase):
    def test_missing_section_errors(self):
        # Strip the "## Edge Cases\n..." block
        broken = VALID_SAMPLE.replace(
            "## Edge Cases\n- Null input handled — SampleService.validate()\n\n",
            ""
        )
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("body missing required section: ## Edge Cases" in e
                            for e in result.errors))

    def test_sections_out_of_order_errors(self):
        # Swap "## Edge Cases" and "## Legacy Notes" positions
        broken = VALID_SAMPLE.replace(
            "## Edge Cases\n- Null input handled — SampleService.validate()\n\n"
            "## Legacy Notes\nnone found\n\n",
            "## Legacy Notes\nnone found\n\n"
            "## Edge Cases\n- Null input handled — SampleService.validate()\n\n"
        )
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("out of order" in e for e in result.errors))

    def test_missing_business_logic_subsection_errors(self):
        # Drop "### Validation Rules" subsection
        broken = VALID_SAMPLE.replace(
            "### Validation Rules\n- Input must be non-null — SampleService.validate()\n\n",
            ""
        )
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("Business Logic missing subsection: ### Validation Rules" in e
                            for e in result.errors))

    def test_all_required_sections_documented(self):
        for name in ("Purpose", "Entry Points", "Business Logic",
                     "Key Classes & Files", "Data Flow", "Database & Storage",
                     "External Dependencies", "Error Handling", "Edge Cases",
                     "Legacy Notes", "Related Skills", "AI Agent Instructions"):
            self.assertIn(name, REQUIRED_BODY_SECTIONS)


class TestContentRules(unittest.TestCase):
    def test_java_code_block_errors(self):
        broken = VALID_SAMPLE.replace(
            "## Database & Storage\n- Tables: sample\n",
            "## Database & Storage\n- Tables: sample\n\n```java\npublic class Foo {}\n```\n"
        )
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("Java code block" in e for e in result.errors))

    def test_data_flow_ascii_fence_does_not_error(self):
        # The valid sample uses a plain ``` fence in Data Flow for ASCII art.
        # That must NOT be flagged.
        result = validate(VALID_SAMPLE)
        self.assertFalse(any("Java code block" in e for e in result.errors))

    def test_empty_section_errors_unless_none_found(self):
        # Make Edge Cases empty (no "none found")
        broken = VALID_SAMPLE.replace(
            "## Edge Cases\n- Null input handled — SampleService.validate()\n",
            "## Edge Cases\n"
        )
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("section 'Edge Cases' is empty" in e for e in result.errors))

    def test_none_found_satisfies_empty_section(self):
        # Replace Edge Cases content with literal "none found"
        replaced = VALID_SAMPLE.replace(
            "## Edge Cases\n- Null input handled — SampleService.validate()\n",
            "## Edge Cases\nnone found\n"
        )
        result = validate(replaced)
        self.assertTrue(result.ok,
                        f"expected 'none found' to satisfy empty section; got {result.errors}")

    def test_empty_business_logic_subsection_errors(self):
        broken = VALID_SAMPLE.replace(
            "### Validation Rules\n- Input must be non-null — SampleService.validate()\n",
            "### Validation Rules\n"
        )
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("Validation Rules" in e and "empty" in e for e in result.errors))


class TestCitationWarning(unittest.TestCase):
    def test_citation_present_no_warning(self):
        result = validate(VALID_SAMPLE)
        self.assertEqual(result.warnings, [])

    def test_citation_missing_warns(self):
        broken = VALID_SAMPLE.replace(
            "- Null input handled — SampleService.validate()",
            "- Null input handled when client sends bad data",
        )
        result = validate(broken)
        # Should still be ok (no errors), but a warning fires
        self.assertTrue(result.ok)
        self.assertTrue(any("Edge Cases" in w and "citation" in w for w in result.warnings))

    def test_none_found_section_does_not_warn(self):
        # External Dependencies is "none found" in sample — that's a citation-free
        # but valid state and must not trigger a warning. Even though External
        # Dependencies isn't in CITATION_REQUIRED_SECTIONS today, the same logic
        # applies to Edge Cases when it's "none found".
        replaced = VALID_SAMPLE.replace(
            "## Edge Cases\n- Null input handled — SampleService.validate()\n",
            "## Edge Cases\nnone found\n"
        )
        result = validate(replaced)
        self.assertTrue(result.ok)
        self.assertEqual(result.warnings, [])


class TestUntaggedJavaFenceDetection(unittest.TestCase):
    """Codex follow-up: ```java fences are caught but an UNTAGGED fence with
    Java keywords inside slips through. Fix: detect Java keywords in untagged
    fenced blocks too. Data Flow's ASCII art (no Java keywords) must still pass."""

    def test_untagged_fence_with_public_class_errors(self):
        broken = VALID_SAMPLE.replace(
            "## Database & Storage\n- Tables: sample\n",
            "## Database & Storage\n- Tables: sample\n\n```\npublic class Foo {}\n```\n"
        )
        result = validate(broken)
        self.assertFalse(result.ok,
                         f"expected error for untagged Java block; got {result.errors}")
        self.assertTrue(any("untagged fence" in e for e in result.errors))

    def test_untagged_fence_with_import_java_errors(self):
        broken = VALID_SAMPLE.replace(
            "## External Dependencies\nnone found\n",
            "## External Dependencies\n\n```\nimport java.util.List;\n```\n"
        )
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("untagged fence" in e for e in result.errors))

    def test_untagged_fence_with_package_decl_errors(self):
        broken = VALID_SAMPLE.replace(
            "## External Dependencies\nnone found\n",
            "## External Dependencies\n\n```\npackage com.acme.foo;\n```\n"
        )
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("untagged fence" in e for e in result.errors))

    def test_data_flow_ascii_diagram_passes(self):
        # The sample's Data Flow has an untagged fence with ASCII art and a
        # ClassName.method() reference — that's NOT Java keywords, must pass.
        result = validate(VALID_SAMPLE)
        self.assertTrue(result.ok)
        self.assertFalse(any("untagged fence" in e for e in result.errors))

    def test_other_language_tag_passes(self):
        broken = VALID_SAMPLE.replace(
            "## External Dependencies\nnone found\n",
            "## External Dependencies\n\n```yaml\nspring:\n  datasource:\n    url: foo\n```\n"
        )
        result = validate(broken)
        self.assertTrue(result.ok,
                        f"non-Java tagged block should pass; got {result.errors}")


class TestPlaceholderContentRejected(unittest.TestCase):
    """Codex follow-up: section content of 'N/A' / 'TBD' / etc. previously
    passed the empty-section check. AGENT.md requires the literal 'none found'."""

    def test_na_rejected(self):
        broken = VALID_SAMPLE.replace(
            "## Edge Cases\n- Null input handled — SampleService.validate()\n",
            "## Edge Cases\nN/A\n"
        )
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("placeholder text" in e for e in result.errors))

    def test_tbd_rejected(self):
        broken = VALID_SAMPLE.replace(
            "## Legacy Notes\nnone found\n",
            "## Legacy Notes\nTBD\n"
        )
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("placeholder text" in e for e in result.errors))

    def test_todo_rejected_case_insensitive(self):
        broken = VALID_SAMPLE.replace(
            "## Legacy Notes\nnone found\n",
            "## Legacy Notes\nTodo\n"
        )
        result = validate(broken)
        self.assertFalse(result.ok)

    def test_real_none_found_passes(self):
        # The sample uses 'none found' in several sections — must keep passing
        result = validate(VALID_SAMPLE)
        self.assertFalse(any("placeholder text" in e for e in result.errors))

    def test_placeholder_in_business_logic_subsection_rejected(self):
        broken = VALID_SAMPLE.replace(
            "### Validation Rules\n- Input must be non-null — SampleService.validate()\n",
            "### Validation Rules\nN/A\n"
        )
        result = validate(broken)
        self.assertFalse(result.ok)
        self.assertTrue(any("Validation Rules" in e and "placeholder" in e for e in result.errors))

    def test_real_content_with_na_word_passes(self):
        # A sentence that contains 'N/A' but isn't ONLY 'N/A' must not be flagged.
        broken = VALID_SAMPLE.replace(
            "## Edge Cases\n- Null input handled — SampleService.validate()\n",
            "## Edge Cases\n- N/A inputs are rejected — SampleService.validate()\n"
        )
        result = validate(broken)
        self.assertTrue(result.ok)


class TestPerBulletCitationWarning(unittest.TestCase):
    """Codex follow-up: section-level citation check passes if ANY bullet in
    the section is cited. Per-bullet warning surfaces specific uncited bullets."""

    def test_uncited_bullet_warns_with_preview(self):
        # Add a second uncited bullet alongside the cited one in Core Flow
        broken = VALID_SAMPLE.replace(
            "### Core Flow\n1. Receive request — SampleController.get()\n2. Process — SampleService.process()\n",
            "### Core Flow\n1. Receive request — SampleController.get()\n2. Process — SampleService.process()\n3. Reject when shutdown\n"
        )
        result = validate(broken)
        self.assertTrue(result.ok,
                        f"per-bullet check is warning-level; got errors: {result.errors}")
        self.assertTrue(any("bullet without" in w and "Reject when shutdown" in w
                            for w in result.warnings))

    def test_all_bullets_cited_no_warning(self):
        result = validate(VALID_SAMPLE)
        self.assertFalse(any("bullet without" in w for w in result.warnings))

    def test_table_rows_skipped(self):
        # A bullet line that's actually a table row (starts with '|') should
        # not be flagged for missing citation
        broken = VALID_SAMPLE.replace(
            "## Edge Cases\n- Null input handled — SampleService.validate()\n",
            "## Edge Cases\n- Null input handled — SampleService.validate()\n- | this looks bullet-like but is tabular |\n"
        )
        result = validate(broken)
        self.assertFalse(any("bullet without" in w and "tabular" in w
                             for w in result.warnings))

    def test_template_hint_skipped(self):
        # Bullets like '- [Step] — ClassName' that are template hints (start
        # with '[') should not be flagged
        broken = VALID_SAMPLE.replace(
            "## Edge Cases\n- Null input handled — SampleService.validate()\n",
            "## Edge Cases\n- Null input handled — SampleService.validate()\n- [example placeholder text]\n"
        )
        result = validate(broken)
        self.assertFalse(any("bullet without" in w and "example placeholder" in w
                             for w in result.warnings))

    def test_none_found_section_no_warning(self):
        # External Dependencies is 'none found' in sample — must not fire
        result = validate(VALID_SAMPLE)
        self.assertFalse(any("External Dependencies" in w for w in result.warnings))


class TestReferenceSkillsAreValid(unittest.TestCase):
    """The three hand-authored reference skills are the documented quality bar.
    They MUST validate cleanly; if a future edit breaks them, this test fires."""

    def test_file_delivery(self):
        path = REPO_ROOT / "skills" / "file-delivery" / "SKILL.md"
        result = validate_file(path)
        self.assertTrue(result.ok,
                        f"file-delivery/SKILL.md should validate; errors: {result.errors}")

    def test_invoice_compare(self):
        path = REPO_ROOT / "skills" / "invoice-compare" / "SKILL.md"
        result = validate_file(path)
        self.assertTrue(result.ok,
                        f"invoice-compare/SKILL.md should validate; errors: {result.errors}")

    def test_payment_method_determination(self):
        path = REPO_ROOT / "skills" / "payment-method-determination" / "SKILL.md"
        result = validate_file(path)
        self.assertTrue(result.ok,
                        f"payment-method-determination/SKILL.md should validate; errors: {result.errors}")


# ---------------------------------------------------------------------------
# validate_paths — the function wired to the `skill-gen validate` subcommand.
# Not covered anywhere in the existing test suite.
# ---------------------------------------------------------------------------

import io
import tempfile
from pathlib import Path as _Path

from tools.skill_generator.validate import validate_paths, print_report


class TestValidatePaths(unittest.TestCase):
    """validate_paths accepts file paths and/or directories; for directories it
    recurses for all SKILL.md files. validate_file is already covered above —
    here we test the dispatch/collection layer."""

    def _write_skill(self, base: _Path, rel: str, content: str = VALID_SAMPLE) -> _Path:
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_explicit_valid_file_returns_single_ok_result(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_skill(_Path(td), "foo/SKILL.md")
            results = validate_paths([str(p)])
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].ok)

    def test_explicit_invalid_file_returns_single_error_result(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_skill(_Path(td), "foo/SKILL.md",
                                  content="# No frontmatter here\n")
            results = validate_paths([str(p)])
            self.assertEqual(len(results), 1)
            self.assertFalse(results[0].ok)

    def test_nonexistent_file_returns_error_result(self):
        results = validate_paths(["/nonexistent/path/SKILL.md"])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertTrue(any("not found" in e for e in results[0].errors))

    def test_empty_path_list_returns_empty_list(self):
        results = validate_paths([])
        self.assertEqual(results, [])

    def test_directory_finds_all_skill_mds_recursively(self):
        with tempfile.TemporaryDirectory() as td:
            root = _Path(td)
            self._write_skill(root, "feat-a/SKILL.md")
            self._write_skill(root, "feat-b/SKILL.md")
            self._write_skill(root, "nested/deep/feat-c/SKILL.md")
            results = validate_paths([str(root)])
            self.assertEqual(len(results), 3,
                             "three SKILL.md files should be found recursively")

    def test_directory_with_no_skill_mds_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            _Path(td, "some_file.txt").write_text("hello", encoding="utf-8")
            results = validate_paths([td])
            self.assertEqual(results, [])

    def test_mix_of_file_and_directory_combined(self):
        with tempfile.TemporaryDirectory() as td:
            root = _Path(td)
            explicit = self._write_skill(root, "explicit/SKILL.md")
            self._write_skill(root, "subdir/feat/SKILL.md")
            results = validate_paths([str(explicit), str(root / "subdir")])
            self.assertEqual(len(results), 2)

    def test_results_have_path_attribute(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_skill(_Path(td), "x/SKILL.md")
            results = validate_paths([str(p)])
            self.assertIsNotNone(results[0].path,
                                 "result.path should be set to the file path")

    def test_three_reference_skill_dirs_all_ok(self):
        """Regression: passing the three artifact-3 reference skill directories
        to validate_paths must return three clean results. (skills/skill-generator/
        is a Claude Agent skill spec, not an artifact-3 file, so we target the
        three reference skill directories explicitly.)"""
        dirs = [
            str(REPO_ROOT / "skills" / "file-delivery"),
            str(REPO_ROOT / "skills" / "invoice-compare"),
            str(REPO_ROOT / "skills" / "payment-method-determination"),
        ]
        results = validate_paths(dirs)
        self.assertEqual(len(results), 3,
                         "expected exactly 3 SKILL.md results, one per directory")
        for r in results:
            self.assertTrue(r.ok,
                            f"{r.path} should validate cleanly; errors: {r.errors}")


# ---------------------------------------------------------------------------
# print_report — returns 0 when no errors, 1 when any errors present.
# Output is written to stdout; the return value controls CLI exit code.
# ---------------------------------------------------------------------------

class TestPrintReport(unittest.TestCase):
    """print_report is the CLI-facing formatter for `skill-gen validate`. It
    prints human-readable output and returns an exit-code-compatible integer."""

    def _run_report(self, results) -> tuple:
        """Capture stdout and return (return_value, printed_text)."""
        import sys
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            rc = print_report(results)
        finally:
            sys.stdout = old_stdout
        return rc, buf.getvalue()

    def test_all_ok_returns_zero(self):
        results = validate_paths([str(REPO_ROOT / "skills" / "file-delivery" / "SKILL.md")])
        rc, _ = self._run_report(results)
        self.assertEqual(rc, 0)

    def test_any_error_returns_one(self):
        with tempfile.TemporaryDirectory() as td:
            p = _Path(td) / "SKILL.md"
            p.write_text("# No frontmatter\n", encoding="utf-8")
            results = validate_paths([str(p)])
        rc, _ = self._run_report(results)
        self.assertEqual(rc, 1)

    def test_output_contains_summary_line(self):
        results = validate_paths([str(REPO_ROOT / "skills" / "file-delivery" / "SKILL.md")])
        _, out = self._run_report(results)
        self.assertIn("validated", out)
        self.assertIn("ok", out)

    def test_empty_results_returns_zero(self):
        rc, _ = self._run_report([])
        self.assertEqual(rc, 0)

    def test_error_count_in_summary(self):
        with tempfile.TemporaryDirectory() as td:
            p = _Path(td) / "SKILL.md"
            p.write_text("# No frontmatter\n", encoding="utf-8")
            results = validate_paths([str(p)])
        _, out = self._run_report(results)
        self.assertIn("error", out.lower())


if __name__ == "__main__":
    unittest.main()
