"""
Smoke tests for tools.skill_generator.plan.

Covers:
  - _parse_plan_json — tolerant JSON extraction used by plan-ingest:
      plain JSON, ```json fence, plain ``` fence, JSON embedded in prose,
      no-JSON raises PlanParseError, invalid JSON raises PlanParseError
  - _slim_index_for_planning — strips full crawl index to the smaller
      Stage-2 prompt payload; verifies method_names and import tokens are
      dropped, and that structural fields survive
  - ingest_response round-trip — parse a minimal response, check the
      returned Plan dataclass has the expected shape and defaults

All tests use stdlib only (tempfile, pathlib, json, unittest).
"""
import json
import tempfile
import unittest
from pathlib import Path

from tools.skill_generator.plan import (
    Plan,
    PlanParseError,
    _parse_plan_json,
    _slim_index_for_planning,
    ingest_response,
)


# ---------------------------------------------------------------------------
# Minimal valid plan JSON that ingest_response / _parse_plan_json can consume
# ---------------------------------------------------------------------------

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
            "description": "Handles file transfers.",
            "classes": ["FileDeliveryService", "FileDeliveryController"],
            "xmlSources": [],
            "sqlSources": [],
            "shellSources": [],
            "configKeys": ["app.file-delivery.*"],
            "confidence": "HIGH",
            "isGodClassSplit": False,
            "godClassParent": None,
            "flags": [],
            "estimatedTokens": 2000,
        }
    ],
}


# ---------------------------------------------------------------------------
# _parse_plan_json
# ---------------------------------------------------------------------------

class TestParsePlanJsonPlain(unittest.TestCase):
    def test_plain_json_object(self):
        raw = json.dumps(_MINIMAL_PLAN)
        result = _parse_plan_json(raw)
        self.assertEqual(result["projectType"], "REST API")
        self.assertEqual(len(result["domains"]), 1)

    def test_json_with_surrounding_whitespace(self):
        raw = "\n\n" + json.dumps(_MINIMAL_PLAN) + "\n"
        result = _parse_plan_json(raw)
        self.assertEqual(result["framework"], "Spring Boot")


class TestParsePlanJsonCodeFence(unittest.TestCase):
    def test_json_fence(self):
        raw = "```json\n" + json.dumps(_MINIMAL_PLAN) + "\n```"
        result = _parse_plan_json(raw)
        self.assertEqual(result["buildSystem"], "Maven")

    def test_plain_fence(self):
        raw = "```\n" + json.dumps(_MINIMAL_PLAN) + "\n```"
        result = _parse_plan_json(raw)
        self.assertEqual(result["javaVersion"], "17")

    def test_fence_without_closing_backticks(self):
        # Host agents sometimes omit the closing fence.
        raw = "```json\n" + json.dumps(_MINIMAL_PLAN)
        result = _parse_plan_json(raw)
        self.assertEqual(result["projectType"], "REST API")


class TestParsePlanJsonEmbeddedInProse(unittest.TestCase):
    def test_json_embedded_after_prose(self):
        raw = (
            "Here is the plan as requested.\n\n"
            + json.dumps(_MINIMAL_PLAN)
            + "\n\nLet me know if you need adjustments."
        )
        result = _parse_plan_json(raw)
        self.assertEqual(result["framework"], "Spring Boot")

    def test_json_with_extra_whitespace_in_fence(self):
        raw = "```json\n\n" + json.dumps(_MINIMAL_PLAN, indent=2) + "\n\n```"
        result = _parse_plan_json(raw)
        self.assertEqual(len(result["domains"]), 1)


class TestParsePlanJsonErrors(unittest.TestCase):
    def test_no_json_raises(self):
        with self.assertRaises(PlanParseError):
            _parse_plan_json("There is no JSON here, sorry.")

    def test_broken_json_raises(self):
        with self.assertRaises(PlanParseError):
            _parse_plan_json('{"projectType": "REST API", broken}')

    def test_empty_string_raises(self):
        with self.assertRaises(PlanParseError):
            _parse_plan_json("")


# ---------------------------------------------------------------------------
# _slim_index_for_planning
# ---------------------------------------------------------------------------

_FULL_INDEX = {
    "scan": {"repo": "/tmp/myrepo"},
    "stats": {"java_classes": 3},
    "java_classes": [
        {
            "file_path": "src/FooService.java",
            "package": "com.example",
            "class_name": "FooService",
            "type": "class",
            "annotations": ["Service"],
            "extends": None,
            "implements": [],
            "line_count": 120,
            "flags": [],
            # Extra fields that should be dropped from the slim version:
            "method_names": ["doWork", "process", "validate", "save", "delete",
                             "find", "fetch", "update", "create", "remove"],
            "import_tail_tokens": ["annotation.Service", "stereotype.Component"],
        }
    ],
    "xml_signals": [{"file_path": "beans.xml", "bean_ids": ["fooService"]}],
    "config_signals": [
        {
            "file_path": "application.yml",
            "config_type": "yaml",
            "key_prefixes": ["app.foo"],
            # key_values is a Stage-3 field and should be passed through if present:
            "key_values": {"app.foo.enabled": "true"},
        }
    ],
    "sql_signals": [],
    "shell_signals": [],
}


class TestSlimIndex(unittest.TestCase):
    def setUp(self):
        self.slim = _slim_index_for_planning(_FULL_INDEX)

    def test_scan_survives(self):
        self.assertEqual(self.slim["scan"], {"repo": "/tmp/myrepo"})

    def test_stats_survive(self):
        self.assertEqual(self.slim["stats"]["java_classes"], 3)

    def test_class_core_fields_survive(self):
        jc = self.slim["java_classes"][0]
        self.assertEqual(jc["class_name"], "FooService")
        self.assertEqual(jc["package"], "com.example")
        self.assertEqual(jc["type"], "class")
        self.assertIn("Service", jc["annotations"])
        self.assertEqual(jc["line_count"], 120)
        self.assertEqual(jc["flags"], [])

    def test_method_names_stripped(self):
        jc = self.slim["java_classes"][0]
        self.assertNotIn("method_names", jc,
                         "method_names must be stripped from the slim index to keep "
                         "the Stage-2 prompt small")

    def test_import_tokens_stripped(self):
        jc = self.slim["java_classes"][0]
        self.assertNotIn("import_tail_tokens", jc)

    def test_xml_signals_survive(self):
        self.assertEqual(len(self.slim["xml_signals"]), 1)
        self.assertEqual(self.slim["xml_signals"][0]["file_path"], "beans.xml")

    def test_config_signals_slim_only(self):
        cs = self.slim["config_signals"][0]
        self.assertIn("file_path", cs)
        self.assertIn("config_type", cs)
        self.assertIn("key_prefixes", cs)

    def test_empty_index_returns_empty_lists(self):
        slim = _slim_index_for_planning({})
        self.assertEqual(slim["java_classes"], [])
        self.assertEqual(slim["xml_signals"], [])
        self.assertEqual(slim["config_signals"], [])
        self.assertEqual(slim["sql_signals"], [])
        self.assertEqual(slim["shell_signals"], [])


# ---------------------------------------------------------------------------
# ingest_response round-trip
# ---------------------------------------------------------------------------

class TestIngestResponse(unittest.TestCase):
    def _write_response(self, tmpdir, content):
        p = Path(tmpdir) / "plan-response.md"
        p.write_text(content, encoding="utf-8")
        return p

    def test_minimal_response_parses_to_plan(self):
        with tempfile.TemporaryDirectory() as td:
            rp = self._write_response(td, json.dumps(_MINIMAL_PLAN))
            plan = ingest_response(rp)
            self.assertIsInstance(plan, Plan)
            self.assertEqual(plan.projectType, "REST API")
            self.assertEqual(plan.framework, "Spring Boot")
            self.assertEqual(len(plan.domains), 1)
            self.assertEqual(plan.domains[0].id, "file-delivery")
            self.assertEqual(plan.domains[0].confidence, "HIGH")
            self.assertFalse(plan.domains[0].isGodClassSplit)

    def test_response_with_fence_parses(self):
        with tempfile.TemporaryDirectory() as td:
            rp = self._write_response(td, "```json\n" + json.dumps(_MINIMAL_PLAN) + "\n```")
            plan = ingest_response(rp)
            self.assertEqual(plan.buildSystem, "Maven")

    def test_plan_persisted_when_path_given(self):
        with tempfile.TemporaryDirectory() as td:
            rp = self._write_response(td, json.dumps(_MINIMAL_PLAN))
            plan_path = Path(td) / ".skill-gen" / "plan.json"
            ingest_response(rp, plan_path)
            self.assertTrue(plan_path.exists(),
                            "plan.json should be written when plan_path is provided")
            stored = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["projectType"], "REST API")

    def test_defaults_filled_for_missing_optional_fields(self):
        minimal = {
            "projectType": "Batch",
            "framework": "Spring Batch",
            "buildSystem": "Maven",
            "javaVersion": "11",
            # No warnings or domains
        }
        with tempfile.TemporaryDirectory() as td:
            rp = self._write_response(td, json.dumps(minimal))
            plan = ingest_response(rp)
            self.assertEqual(plan.warnings, [])
            self.assertEqual(plan.domains, [])

    def test_domain_defaults_filled(self):
        plan_with_sparse_domain = dict(_MINIMAL_PLAN)
        plan_with_sparse_domain["domains"] = [{"id": "sparse-domain"}]
        with tempfile.TemporaryDirectory() as td:
            rp = self._write_response(td, json.dumps(plan_with_sparse_domain))
            plan = ingest_response(rp)
            d = plan.domains[0]
            self.assertEqual(d.id, "sparse-domain")
            self.assertEqual(d.name, "sparse-domain")  # falls back to id
            self.assertEqual(d.classes, [])
            self.assertEqual(d.confidence, "MEDIUM")
            self.assertFalse(d.isGodClassSplit)
            self.assertIsNone(d.godClassParent)


if __name__ == "__main__":
    unittest.main()
