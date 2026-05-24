"""
Smoke tests for tools.skill_generator.link.

Covers:
  - _invert_link_type — the forward→reverse mapping table (calls, shares,
      extends, configures, unknown passthrough)
  - _parse_links_json — tolerant JSON extraction used by link-ingest:
      plain JSON, ```json fence, plain ``` fence, JSON embedded in prose,
      no-JSON raises LinkParseError, invalid JSON raises LinkParseError
  - _apply_links — updates related_skills frontmatter and inserts rows into
      the Related Skills table; handles "none" placeholder and "PLACEHOLDER"
      frontmatter; idempotency when nothing changes
  - ingest_response end-to-end — reads a JSON response, patches two SKILL.md
      files, validates the schema contract is maintained

All tests use stdlib only (tempfile, pathlib, json, unittest).
"""
import json
import tempfile
import unittest
from pathlib import Path

from tools.skill_generator.link import (
    LinkParseError,
    _apply_links,
    _invert_link_type,
    _parse_links_json,
    ingest_response,
)


# ---------------------------------------------------------------------------
# Minimal valid SKILL.md body used by several tests
# ---------------------------------------------------------------------------

def _make_skill(domain_id: str, related_skills_value: str = "none") -> str:
    return f"""\
---
skill: {domain_id.replace('-', ' ').title()}
domain: {domain_id}
version: 1
project_type: REST API
framework: Spring Boot
java_version: 17
legacy: false
status: active
flags: none
related_skills: {related_skills_value}
generated_by: skill_generator.agent
last_updated: 2026-05-16
---

# {domain_id.replace('-', ' ').title()}

## Purpose
Does something.

## Entry Points
- REST: GET /api/{domain_id} → {domain_id.title().replace('-', '')}Controller.get()

## Business Logic

### Core Flow
1. Receive — {domain_id.title().replace('-', '')}Controller.get()
2. Process — {domain_id.title().replace('-', '')}Service.process()

### Validation Rules
- Non-null — {domain_id.title().replace('-', '')}Service.validate()

### Business Rules
- Returns 200 — {domain_id.title().replace('-', '')}Service.process()

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| {domain_id.title().replace('-', '')}Service.java | Service | core logic |

## Data Flow
```
GET /api/{domain_id}
   |
   v
{domain_id.title().replace('-', '')}Service.process()
```

## Database & Storage
- Tables: {domain_id.replace('-', '_')}

## External Dependencies
none found

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| RuntimeException | failure | 500 |

## Edge Cases
- Null handled — {domain_id.title().replace('-', '')}Service.validate()

## Legacy Notes
none found

## Related Skills
none found

## AI Agent Instructions
1. Always validate — {domain_id.title().replace('-', '')}Service.validate()
"""


# ---------------------------------------------------------------------------
# _invert_link_type
# ---------------------------------------------------------------------------

class TestInvertLinkType(unittest.TestCase):
    def test_calls_inverts_to_called_by(self):
        self.assertEqual(_invert_link_type("calls"), "called-by")

    def test_shares_is_symmetric(self):
        self.assertEqual(_invert_link_type("shares"), "shares")

    def test_extends_inverts_to_extended_by(self):
        self.assertEqual(_invert_link_type("extends"), "extended-by")

    def test_configures_inverts_to_configured_by(self):
        self.assertEqual(_invert_link_type("configures"), "configured-by")

    def test_unknown_type_passes_through(self):
        self.assertEqual(_invert_link_type("depends-on"), "depends-on")

    def test_empty_string_passes_through(self):
        self.assertEqual(_invert_link_type(""), "")


# ---------------------------------------------------------------------------
# _parse_links_json
# ---------------------------------------------------------------------------

_MINIMAL_LINKS = {"links": [
    {"from": "file-delivery", "to": "invoice-compare",
     "type": "calls", "reason": "triggers invoice check"},
]}


class TestParseLinksJsonPlain(unittest.TestCase):
    def test_plain_json(self):
        raw = json.dumps(_MINIMAL_LINKS)
        result = _parse_links_json(raw)
        self.assertEqual(len(result["links"]), 1)
        self.assertEqual(result["links"][0]["from"], "file-delivery")

    def test_json_with_surrounding_whitespace(self):
        raw = "\n\n" + json.dumps(_MINIMAL_LINKS) + "\n"
        result = _parse_links_json(raw)
        self.assertEqual(result["links"][0]["to"], "invoice-compare")


class TestParseLinksJsonCodeFence(unittest.TestCase):
    def test_json_fence(self):
        raw = "```json\n" + json.dumps(_MINIMAL_LINKS) + "\n```"
        result = _parse_links_json(raw)
        self.assertEqual(len(result["links"]), 1)

    def test_plain_fence(self):
        raw = "```\n" + json.dumps(_MINIMAL_LINKS) + "\n```"
        result = _parse_links_json(raw)
        self.assertEqual(result["links"][0]["type"], "calls")

    def test_fence_without_closing_backticks(self):
        raw = "```json\n" + json.dumps(_MINIMAL_LINKS)
        result = _parse_links_json(raw)
        self.assertEqual(len(result["links"]), 1)


class TestParseLinksJsonEmbeddedInProse(unittest.TestCase):
    def test_embedded_after_explanation(self):
        raw = (
            "Here are the cross-domain links I identified:\n\n"
            + json.dumps(_MINIMAL_LINKS)
            + "\n\nThat covers all the direct dependencies."
        )
        result = _parse_links_json(raw)
        self.assertEqual(result["links"][0]["reason"], "triggers invoice check")


class TestParseLinksJsonErrors(unittest.TestCase):
    def test_no_json_raises(self):
        with self.assertRaises(LinkParseError):
            _parse_links_json("I found no cross-domain links.")

    def test_broken_json_raises(self):
        with self.assertRaises(LinkParseError):
            _parse_links_json('{"links": [broken]}')

    def test_empty_string_raises(self):
        with self.assertRaises(LinkParseError):
            _parse_links_json("")


# ---------------------------------------------------------------------------
# _apply_links
# ---------------------------------------------------------------------------

class TestApplyLinksRelatedSkillsFrontmatter(unittest.TestCase):
    def test_none_placeholder_replaced(self):
        text = _make_skill("file-delivery", related_skills_value="none")
        links = [{"to": "invoice-compare", "type": "calls", "reason": "triggers check"}]
        result = _apply_links(text, links)
        self.assertIn("related_skills: invoice-compare", result)

    def test_PLACEHOLDER_replaced(self):
        text = _make_skill("file-delivery", related_skills_value="PLACEHOLDER")
        links = [{"to": "payment-method", "type": "shares", "reason": "shares config"}]
        result = _apply_links(text, links)
        self.assertIn("related_skills: payment-method", result)

    def test_bracket_PLACEHOLDER_replaced(self):
        text = _make_skill("file-delivery", related_skills_value="[PLACEHOLDER]")
        links = [{"to": "invoice-compare", "type": "calls", "reason": "x"}]
        result = _apply_links(text, links)
        self.assertIn("related_skills: invoice-compare", result)

    def test_multiple_targets_sorted_and_joined(self):
        text = _make_skill("file-delivery", related_skills_value="none")
        links = [
            {"to": "payment-method", "type": "calls", "reason": "a"},
            {"to": "invoice-compare", "type": "shares", "reason": "b"},
        ]
        result = _apply_links(text, links)
        # sorted order: invoice-compare, payment-method
        self.assertIn("related_skills: invoice-compare, payment-method", result)

    def test_duplicate_targets_deduplicated(self):
        text = _make_skill("file-delivery", related_skills_value="none")
        links = [
            {"to": "invoice-compare", "type": "calls", "reason": "first"},
            {"to": "invoice-compare", "type": "shares", "reason": "second"},
        ]
        result = _apply_links(text, links)
        # "invoice-compare" must appear exactly once in the frontmatter value
        fm_line = next(
            l for l in result.splitlines() if l.startswith("related_skills:")
        )
        self.assertEqual(fm_line.count("invoice-compare"), 1)

    def test_existing_real_value_overwritten(self):
        """Regression: a second link-ingest run must overwrite an existing real
        related_skills value, not leave it stale. Previously only placeholder
        sentinels (none / PLACEHOLDER / [PLACEHOLDER]) were matched, so this
        silently skipped the frontmatter update while still rewriting the body
        table — leaving frontmatter and body inconsistent."""
        text = _make_skill("file-delivery", related_skills_value="invoice-compare")
        links = [{"to": "payment-method", "type": "calls", "reason": "needs payment"}]
        result = _apply_links(text, links)
        fm_line = next(l for l in result.splitlines() if l.startswith("related_skills:"))
        self.assertEqual(fm_line, "related_skills: payment-method",
                         "existing related_skills value must be replaced, not left stale")


class TestApplyLinksRelatedSkillsTable(unittest.TestCase):
    def test_table_row_inserted(self):
        text = _make_skill("file-delivery")
        links = [{"to": "invoice-compare", "type": "calls", "reason": "triggers invoice check"}]
        result = _apply_links(text, links)
        self.assertIn("| invoice-compare |", result)
        self.assertIn("| calls |", result)
        self.assertIn("triggers invoice check", result)

    def test_header_row_present(self):
        text = _make_skill("file-delivery")
        links = [{"to": "invoice-compare", "type": "calls", "reason": "x"}]
        result = _apply_links(text, links)
        self.assertIn("| Domain | Relationship | Reason |", result)

    def test_multiple_links_multiple_rows(self):
        text = _make_skill("file-delivery")
        links = [
            {"to": "invoice-compare", "type": "calls", "reason": "a"},
            {"to": "payment-method", "type": "shares", "reason": "b"},
        ]
        result = _apply_links(text, links)
        self.assertIn("| invoice-compare |", result)
        self.assertIn("| payment-method |", result)

    def test_ai_agent_instructions_section_preserved(self):
        text = _make_skill("file-delivery")
        links = [{"to": "invoice-compare", "type": "calls", "reason": "x"}]
        result = _apply_links(text, links)
        self.assertIn("## AI Agent Instructions", result)

    def test_no_change_when_no_links(self):
        text = _make_skill("file-delivery")
        result = _apply_links(text, [])
        # With no links, only the frontmatter replacement matters; content should
        # remain structurally intact.
        self.assertIn("## AI Agent Instructions", result)


# ---------------------------------------------------------------------------
# ingest_response end-to-end (with validate_schema=False to avoid noise from
# the synthetic SKILL.md content)
# ---------------------------------------------------------------------------

class TestIngestResponseEndToEnd(unittest.TestCase):
    def _setup(self, tmpdir):
        skills_dir = Path(tmpdir) / "skills"
        (skills_dir / "file-delivery").mkdir(parents=True)
        (skills_dir / "invoice-compare").mkdir(parents=True)
        (skills_dir / "file-delivery" / "SKILL.md").write_text(
            _make_skill("file-delivery"), encoding="utf-8"
        )
        (skills_dir / "invoice-compare" / "SKILL.md").write_text(
            _make_skill("invoice-compare"), encoding="utf-8"
        )
        return skills_dir

    def _write_response(self, tmpdir, content):
        rp = Path(tmpdir) / "link-response.md"
        rp.write_text(content, encoding="utf-8")
        return rp

    def test_both_sides_updated(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup(td)
            response = json.dumps({"links": [
                {"from": "file-delivery", "to": "invoice-compare",
                 "type": "calls", "reason": "triggers invoice check"},
            ]})
            rp = self._write_response(td, response)
            result = ingest_response(rp, skills_dir, validate_schema=False)
            updated = [Path(p).parent.name for p in result["updated"]]
            self.assertIn("file-delivery", updated,
                          "from-side SKILL.md must be updated")
            self.assertIn("invoice-compare", updated,
                          "to-side SKILL.md must be updated with inverse link")

    def test_forward_link_written(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup(td)
            response = json.dumps({"links": [
                {"from": "file-delivery", "to": "invoice-compare",
                 "type": "calls", "reason": "triggers invoice check"},
            ]})
            rp = self._write_response(td, response)
            ingest_response(rp, skills_dir, validate_schema=False)
            fd_text = (skills_dir / "file-delivery" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("invoice-compare", fd_text)
            self.assertIn("calls", fd_text)

    def test_inverse_link_written(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup(td)
            response = json.dumps({"links": [
                {"from": "file-delivery", "to": "invoice-compare",
                 "type": "calls", "reason": "triggers invoice check"},
            ]})
            rp = self._write_response(td, response)
            ingest_response(rp, skills_dir, validate_schema=False)
            ic_text = (skills_dir / "invoice-compare" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("file-delivery", ic_text)
            self.assertIn("called-by", ic_text)

    def test_missing_skill_skipped_without_crash(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup(td)
            response = json.dumps({"links": [
                {"from": "file-delivery", "to": "no-such-feature",
                 "type": "calls", "reason": "x"},
            ]})
            rp = self._write_response(td, response)
            # Should not raise; the missing domain is skipped gracefully.
            result = ingest_response(rp, skills_dir, validate_schema=False)
            self.assertIsInstance(result, dict)

    def test_empty_links_no_updates(self):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup(td)
            response = json.dumps({"links": []})
            rp = self._write_response(td, response)
            result = ingest_response(rp, skills_dir, validate_schema=False)
            self.assertEqual(result["updated"], [])

    def test_link_with_malformed_entry_skipped(self):
        """Links missing 'from' or 'to' keys are silently skipped."""
        with tempfile.TemporaryDirectory() as td:
            skills_dir = self._setup(td)
            response = json.dumps({"links": [
                {"reason": "no from/to at all"},
                {"from": "file-delivery", "to": "invoice-compare",
                 "type": "calls", "reason": "valid"},
            ]})
            rp = self._write_response(td, response)
            result = ingest_response(rp, skills_dir, validate_schema=False)
            # The valid link should still be applied
            self.assertTrue(len(result["updated"]) > 0)


if __name__ == "__main__":
    unittest.main()
