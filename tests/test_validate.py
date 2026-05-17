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


if __name__ == "__main__":
    unittest.main()
