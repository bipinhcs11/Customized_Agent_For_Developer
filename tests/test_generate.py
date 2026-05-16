"""
Smoke tests for tools.skill_generator.generate.

Covers:
  - _collect_source_blob with simple class names (sanity)
  - _collect_source_blob with FQN class names — regression for the bug where
    c.split(".")[0] on "com.example.FooService" returned "com" instead of
    "FooService", silently producing empty source blobs.
  - _strip_markdown_fence (used by both generate-ingest and update-ingest)
  - _build_prompt (template substitution)
"""
import tempfile
import unittest
from pathlib import Path

from tools.skill_generator.generate import (
    _collect_source_blob,
    _build_prompt,
    _strip_markdown_fence,
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


if __name__ == "__main__":
    unittest.main()
