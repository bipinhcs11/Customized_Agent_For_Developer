"""
Smoke tests for tools.skill_generator.crawler.

Covers:
  - Pure helpers: _strip_java_noise, _split_csv_types, _import_tail_tokens,
    _extract_properties_prefixes, _extract_yaml_prefixes, _normalize_java_version
  - File parsers: parse_java_file, parse_sql_file
  - The _iter_files exclude logic — specifically the bug where absolute path
    components (e.g. the parent dir being named "build") would cause all files
    to be silently skipped.
  - crawl() end-to-end on a minimal temp repo.

All tests use stdlib only (tempfile, pathlib, unittest).
"""
import tempfile
import unittest
from pathlib import Path

from tools.skill_generator.crawler import (
    _extract_properties_prefixes,
    _extract_yaml_prefixes,
    _import_tail_tokens,
    _normalize_java_version,
    _split_csv_types,
    _strip_java_noise,
    crawl,
    parse_java_file,
    parse_sql_file,
    _iter_files,
    DEFAULT_EXCLUDE_DIRS,
)


class TestStripJavaNoise(unittest.TestCase):
    def test_removes_block_comment(self):
        src = "/* This is a comment */ class Foo {}"
        result = _strip_java_noise(src)
        self.assertNotIn("This is a comment", result)
        self.assertIn("class Foo", result)

    def test_removes_line_comment(self):
        src = "int x = 1; // this is inline\nint y = 2;"
        result = _strip_java_noise(src)
        self.assertNotIn("this is inline", result)
        self.assertIn("int y = 2", result)

    def test_replaces_string_literal(self):
        src = 'String s = "hello @World";'
        result = _strip_java_noise(src)
        self.assertNotIn("hello", result)
        self.assertIn('""', result)

    def test_annotation_inside_comment_not_extracted(self):
        src = "// @Deprecated\nclass Foo {}"
        result = _strip_java_noise(src)
        self.assertNotIn("@Deprecated", result)


class TestSplitCsvTypes(unittest.TestCase):
    def test_single(self):
        self.assertEqual(_split_csv_types("Foo"), ["Foo"])

    def test_two(self):
        self.assertEqual(_split_csv_types("Foo, Bar"), ["Foo", "Bar"])

    def test_generics_stripped(self):
        self.assertEqual(
            _split_csv_types("JpaRepository<FileDeliveryEntity, Long>"),
            ["JpaRepository"],
        )

    def test_none(self):
        self.assertEqual(_split_csv_types(None), [])

    def test_empty(self):
        self.assertEqual(_split_csv_types(""), [])


class TestImportTailTokens(unittest.TestCase):
    def test_basic(self):
        imports = ["org.springframework.web.bind.annotation.RestController"]
        result = _import_tail_tokens(imports)
        self.assertEqual(result, ["annotation.RestController"])

    def test_cap_at_limit(self):
        imports = [f"com.example.pkg{i}.Class{i}" for i in range(20)]
        result = _import_tail_tokens(imports)
        self.assertLessEqual(len(result), 6)

    def test_deduplication(self):
        imports = ["a.b.Foo", "c.d.Foo"]
        result = _import_tail_tokens(imports)
        self.assertEqual(result.count("b.Foo"), 1)

    def test_short_import(self):
        result = _import_tail_tokens(["Foo"])
        self.assertEqual(result, ["Foo"])


class TestNormalizeJavaVersion(unittest.TestCase):
    def test_old_style(self):
        self.assertEqual(_normalize_java_version("1.8"), "8")

    def test_modern(self):
        self.assertEqual(_normalize_java_version("17"), "17")

    def test_version_prefix(self):
        self.assertEqual(_normalize_java_version("VERSION_17"), "17")

    def test_with_v_prefix(self):
        self.assertEqual(_normalize_java_version("v11"), "11")

    def test_major_only(self):
        self.assertEqual(_normalize_java_version("21.0"), "21")


class TestExtractPropertiesPrefixes(unittest.TestCase):
    def test_basic(self):
        text = "spring.datasource.url=jdbc:postgresql://localhost/db\nserver.port=8080\n"
        result = _extract_properties_prefixes(text)
        self.assertIn("spring.datasource", result)
        self.assertIn("server.port", result)

    def test_skip_comments(self):
        text = "# spring.mail.host=localhost\napp.name=test\n"
        result = _extract_properties_prefixes(text)
        self.assertNotIn("spring.mail", result)
        self.assertIn("app.name", result)

    def test_empty(self):
        self.assertEqual(_extract_properties_prefixes(""), [])


class TestExtractYamlPrefixes(unittest.TestCase):
    def test_basic(self):
        text = "spring:\n  datasource:\n    url: jdbc:...\nserver:\n  port: 8080\n"
        result = _extract_yaml_prefixes(text)
        self.assertIn("spring", result)
        self.assertIn("spring.datasource", result)
        self.assertIn("server", result)

    def test_skips_comments(self):
        text = "# comment\napp:\n  name: test\n"
        result = _extract_yaml_prefixes(text)
        self.assertIn("app", result)


class TestParseJavaFile(unittest.TestCase):
    def _write(self, tmpdir, name, content):
        p = Path(tmpdir) / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_simple_class(self):
        with tempfile.TemporaryDirectory() as td:
            src = (
                "package com.example;\n"
                "import org.springframework.stereotype.Service;\n"
                "@Service\n"
                "public class FooService {\n"
                "    public void doWork() {}\n"
                "}\n"
            )
            p = self._write(td, "FooService.java", src)
            results, warn = parse_java_file(p, Path(td))
            self.assertIsNone(warn)
            self.assertEqual(len(results), 1)
            jc = results[0]
            self.assertEqual(jc.class_name, "FooService")
            self.assertEqual(jc.package, "com.example")
            self.assertEqual(jc.type, "class")
            self.assertIn("Service", jc.annotations)
            self.assertIn("doWork", jc.method_names)

    def test_skips_generated(self):
        with tempfile.TemporaryDirectory() as td:
            src = "// DO NOT EDIT\npublic class Generated {}\n"
            p = self._write(td, "Generated.java", src)
            results, warn = parse_java_file(p, Path(td))
            self.assertIsNone(warn)
            self.assertEqual(results, [])

    def test_enum_type(self):
        with tempfile.TemporaryDirectory() as td:
            src = "package com.example;\npublic enum Status { ACTIVE, INACTIVE }\n"
            p = self._write(td, "Status.java", src)
            results, warn = parse_java_file(p, Path(td))
            self.assertIsNone(warn)
            self.assertEqual(results[0].type, "enum")

    def test_god_class_flag(self):
        with tempfile.TemporaryDirectory() as td:
            lines = ["public class Big {"] + ["    // line\n" for _ in range(350)] + ["}"]
            p = self._write(td, "Big.java", "\n".join(lines))
            results, _ = parse_java_file(p, Path(td))
            self.assertIn("god_class", results[0].flags)

    def test_test_file_flag(self):
        with tempfile.TemporaryDirectory() as td:
            src = "public class FooTest {}\n"
            p = self._write(td, "FooTest.java", src)
            results, _ = parse_java_file(p, Path(td))
            self.assertIn("test", results[0].flags)

    def test_deprecated_flag(self):
        with tempfile.TemporaryDirectory() as td:
            src = "@Deprecated\npublic class OldService {}\n"
            p = self._write(td, "OldService.java", src)
            results, _ = parse_java_file(p, Path(td))
            self.assertIn("deprecated", results[0].flags)


class TestParseSqlFile(unittest.TestCase):
    def test_create_table(self):
        with tempfile.TemporaryDirectory() as td:
            sql = "CREATE TABLE file_delivery (id BIGINT PRIMARY KEY);\n"
            p = Path(td) / "schema.sql"
            p.write_text(sql)
            result, warn = parse_sql_file(p, Path(td))
            self.assertIsNone(warn)
            self.assertIsNotNone(result)
            self.assertIn("file_delivery", result.tables)
            self.assertEqual(result.sql_kind, "ddl")

    def test_stored_procedure(self):
        with tempfile.TemporaryDirectory() as td:
            sql = "CREATE OR REPLACE PROCEDURE process_batch() BEGIN END;\n"
            p = Path(td) / "procs.sql"
            p.write_text(sql)
            result, _ = parse_sql_file(p, Path(td))
            self.assertIn("process_batch", result.procedures)
            self.assertEqual(result.sql_kind, "stored_proc")
            self.assertIn("callable_from_java", result.flags)

    def test_flyway_naming(self):
        with tempfile.TemporaryDirectory() as td:
            sql = "CREATE TABLE orders (id INT);\n"
            p = Path(td) / "V1__create_orders.sql"
            p.write_text(sql)
            result, _ = parse_sql_file(p, Path(td))
            self.assertIn("flyway_migration", result.flags)
            self.assertEqual(result.sql_kind, "migration")

    def test_empty_file_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty.sql"
            p.write_text("-- just a comment\n")
            result, warn = parse_sql_file(p, Path(td))
            self.assertIsNone(result)


class TestIterFilesExcludeByRelativeParts(unittest.TestCase):
    """
    Regression test for the bug where _iter_files used path.parts (absolute)
    instead of path.relative_to(repo_root).parts when filtering excluded dirs.

    If the repo is checked out at a path whose ancestor directory is named
    "build", "target", "generated", etc., the old code would exclude every
    single file because those names appeared in the absolute path parts.
    """

    def test_repo_under_build_dir_not_excluded(self):
        """Files inside the repo are found even when the repo root's parent
        directory happens to be named after an excluded dir (e.g. 'build')."""
        with tempfile.TemporaryDirectory() as td:
            # Simulate: /tmp/.../build/myrepo/src/Foo.java
            build_parent = Path(td) / "build"
            repo_root = build_parent / "myrepo"
            src_dir = repo_root / "src"
            src_dir.mkdir(parents=True)
            (src_dir / "Foo.java").write_text("public class Foo {}\n")

            files = list(_iter_files(repo_root, set()))
            names = [f.name for f in files]
            self.assertIn("Foo.java", names,
                          "Foo.java should be found even though repo lives inside a 'build' dir")

    def test_repo_under_target_dir_not_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "target" / "myproject"
            (repo_root / "src").mkdir(parents=True)
            (repo_root / "src" / "Bar.java").write_text("public class Bar {}\n")

            files = list(_iter_files(repo_root, set()))
            names = [f.name for f in files]
            self.assertIn("Bar.java", names)

    def test_internal_build_dir_is_still_excluded(self):
        """A 'build/' directory *inside* the repo (typical Gradle output) is excluded."""
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "myrepo"
            (repo_root / "build" / "classes").mkdir(parents=True)
            (repo_root / "build" / "classes" / "Compiled.java").write_text("class Compiled {}\n")
            (repo_root / "src").mkdir()
            (repo_root / "src" / "Real.java").write_text("class Real {}\n")

            files = list(_iter_files(repo_root, set()))
            names = [f.name for f in files]
            self.assertIn("Real.java", names)
            self.assertNotIn("Compiled.java", names,
                             "Files inside the repo's own build/ dir should be excluded")


class TestIterFilesDeterministicOrder(unittest.TestCase):
    """_iter_files must return files sorted by relative path, regardless of
    the order the underlying filesystem yields directory entries. Without
    this, the crawl index (and everything downstream — plan/generate prompts)
    would vary between machines/checkouts of the same repo content."""

    def test_files_sorted_by_relative_path(self):
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            (repo_root / "src").mkdir()
            # Create files in reverse-alphabetical order so creation order
            # cannot accidentally match the expected sorted order.
            (repo_root / "Zebra.java").write_text("class Zebra {}\n")
            (repo_root / "src" / "Beta.java").write_text("class Beta {}\n")
            (repo_root / "Alpha.java").write_text("class Alpha {}\n")

            files = list(_iter_files(repo_root, set()))
            rel_paths = [f.relative_to(repo_root).as_posix() for f in files]
            self.assertEqual(rel_paths, sorted(rel_paths))
            self.assertEqual(rel_paths, ["Alpha.java", "Zebra.java", "src/Beta.java"])

    def test_crawl_java_classes_sorted_by_file_path(self):
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            (repo_root / "Zebra.java").write_text("public class Zebra {}\n")
            (repo_root / "Alpha.java").write_text("public class Alpha {}\n")
            (repo_root / "Mango.java").write_text("public class Mango {}\n")

            index = crawl(repo_root)
            file_paths = [jc.file_path for jc in index.java_classes]
            self.assertEqual(file_paths, sorted(file_paths))


class TestCrawlEndToEnd(unittest.TestCase):
    def test_minimal_repo(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "myrepo"
            src = repo / "src" / "main" / "java" / "com" / "example"
            src.mkdir(parents=True)
            (src / "OrderService.java").write_text(
                "package com.example;\n"
                "@org.springframework.stereotype.Service\n"
                "public class OrderService {\n"
                "    public void placeOrder() {}\n"
                "}\n"
            )
            # A file that should be skipped (inside target/)
            (repo / "target").mkdir()
            (repo / "target" / "OrderService.class").write_text("binary")

            index = crawl(repo)
            self.assertGreaterEqual(index.stats["java_classes"], 1)
            names = [jc.class_name for jc in index.java_classes]
            self.assertIn("OrderService", names)

    def test_empty_repo_warns(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "empty"
            repo.mkdir()
            index = crawl(repo)
            self.assertEqual(index.stats["java_classes"], 0)
            self.assertTrue(
                any("zero-source-files" in w for w in index.warnings),
                "Expected a zero-source-files warning for an empty repo",
            )

    def test_no_api_calls(self):
        """crawl() must never make network calls — just verify it completes
        without importing any network module."""
        import sys
        net_modules_before = {k for k in sys.modules if "urllib" in k or "http" in k}
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "Foo.java").write_text("public class Foo {}\n")
            crawl(repo)
        net_modules_after = {k for k in sys.modules if "urllib" in k or "http" in k}
        self.assertEqual(net_modules_before, net_modules_after,
                         "crawl() must not import network modules")


if __name__ == "__main__":
    unittest.main()
