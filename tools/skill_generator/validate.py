"""
SKILL.md validator — enforces the artifact-3 SKILL.md contract.

Until this module existed, every ingest stage (`generate-ingest`,
`update-ingest`, `link-ingest`) trusted whatever the host agent returned
and wrote it straight to disk. That made the tool only as good as the
quietest copy-paste mistake. This module is the gate: it verifies that
frontmatter is complete, body sections are present in the required order,
empty sections use the literal "none found", the body contains no Java
code blocks, and the citation requirement is met where the SKILL.md has
real content.

Used by:
  - generate.py  (generate-ingest) — blocks the write if invalid
  - update.py    (update-ingest)   — blocks the write if invalid
  - link.py      (link-ingest)     — blocks the rewrite if it breaks the contract
  - cli.py       (skill-gen validate) — ad-hoc validation of any SKILL.md

Stdlib-only by design — no PyYAML. The frontmatter we care about is
line-oriented `key: value`, which a few lines of regex parse correctly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


REQUIRED_FRONTMATTER_FIELDS = [
    "skill", "domain", "version", "project_type", "framework",
    "java_version", "legacy", "status", "flags", "related_skills",
    "generated_by", "last_updated",
]

REQUIRED_BODY_SECTIONS = [
    "Purpose",
    "Entry Points",
    "Business Logic",
    "Key Classes & Files",
    "Data Flow",
    "Database & Storage",
    "External Dependencies",
    "Error Handling",
    "Edge Cases",
    "Legacy Notes",
    "Related Skills",
    "AI Agent Instructions",
]

REQUIRED_BUSINESS_LOGIC_SUBSECTIONS = ["Core Flow", "Validation Rules", "Business Rules"]

# Sections/subsections that must cite ClassName.methodName() when non-empty.
# Warning-level only — citation detection has false negatives (e.g., `$` in
# inner class names is not matched), so we report the absence as a warning
# rather than an error.
CITATION_REQUIRED_SECTIONS = [
    "Entry Points", "Core Flow", "Validation Rules", "Business Rules", "Edge Cases",
]

NONE_FOUND = "none found"

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n(.*))?\Z", re.DOTALL)
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
JAVA_FENCE_RE = re.compile(r"^```\s*[Jj]ava\b", re.MULTILINE)
CITATION_RE = re.compile(r"\b[A-Z][A-Za-z0-9_]*\.[a-z_][A-Za-z0-9_]*\(")

# Match any fenced block — used by the untagged-Java detector to look inside
# blocks whose language tag is empty (Data Flow ASCII art etc.) and decide
# whether the content is actually Java code.
ANY_FENCE_RE = re.compile(r"^```(\S*)\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)

# Strong Java signals that won't appear in prose or Data Flow ASCII trees.
# Tightened deliberately — we'd rather miss a borderline snippet than flag
# legitimate diagram content.
JAVA_CODE_KEYWORDS_RE = re.compile(
    r"\b(public\s+(?:class|interface|enum|static)|"
    r"private\s+(?:class|static)|"
    r"protected\s+(?:class|static)|"
    r"import\s+java\.|"
    r"package\s+[a-z][\w.]*\s*;)",
    re.MULTILINE,
)

# Lines that look like bullets or numbered-list items inside a section body.
# Captures the text after the bullet marker so we can check it for a citation.
BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.+)$", re.MULTILINE)

# Strings developers sometimes use instead of writing real content or the
# literal "none found". Lower-cased for case-insensitive comparison.
PLACEHOLDER_STRINGS = {
    "n/a", "na", "tbd", "todo", "placeholder", "xxx",
    "?", "??", "???", "---", "tbc",
}


@dataclass
class ValidationResult:
    path: str
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def format_report(self) -> str:
        lines = [f"== {self.path} =="]
        if not self.errors and not self.warnings:
            lines.append("  OK")
            return "\n".join(lines)
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings:
            lines.append(f"  WARN:  {w}")
        return "\n".join(lines)


def validate(skill_md: str, path: str = "<unknown>") -> ValidationResult:
    """Validate a SKILL.md string against the artifact-3 contract."""
    result = ValidationResult(path=path)
    text = skill_md.lstrip("﻿")  # strip BOM

    frontmatter, body = _split_frontmatter(text)
    if frontmatter is None:
        result.errors.append(
            "missing YAML frontmatter (must start with '---' on the first line and close with '---')"
        )
        return result

    _check_frontmatter(frontmatter, result)
    _check_body_sections(body, result)
    _check_business_logic_subsections(body, result)
    _check_no_java_blocks(body, result)
    _check_no_placeholder_content(body, result)
    _check_none_found_for_empty(body, result)
    _check_citations(body, result)
    _check_per_bullet_citations(body, result)

    return result


def validate_file(path) -> ValidationResult:
    """Validate a SKILL.md on disk."""
    p = Path(path)
    if not p.exists():
        r = ValidationResult(path=str(p))
        r.errors.append(f"file not found: {p}")
        return r
    return validate(p.read_text(encoding="utf-8"), str(p))


def validate_paths(paths) -> list:
    """Validate a list of files and/or directories. For each directory, all
    SKILL.md files under it (recursive) are validated."""
    results: list = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for sf in sorted(path.glob("**/SKILL.md")):
                results.append(validate_file(sf))
        else:
            results.append(validate_file(path))
    return results


def print_report(results) -> int:
    """Print a human-readable report. Returns 0 if no errors, 1 otherwise."""
    error_count = 0
    warn_count = 0
    for r in results:
        print(r.format_report())
        error_count += len(r.errors)
        warn_count += len(r.warnings)
    ok_count = sum(1 for r in results if r.ok)
    print()
    print(
        f"validated {len(results)} file(s): "
        f"{ok_count} ok, {len(results) - ok_count} with errors, "
        f"{error_count} error(s), {warn_count} warning(s)"
    )
    return 0 if error_count == 0 else 1


# ─── Frontmatter ──────────────────────────────────────────────────────────────

def _split_frontmatter(text: str):
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    return m.group(1), m.group(2) or ""


def _frontmatter_pairs(frontmatter: str) -> dict:
    pairs: dict = {}
    for line in frontmatter.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if m:
            pairs[m.group(1)] = m.group(2).strip()
    return pairs


def _check_frontmatter(frontmatter: str, result: ValidationResult) -> None:
    pairs = _frontmatter_pairs(frontmatter)
    for fld in REQUIRED_FRONTMATTER_FIELDS:
        if fld not in pairs:
            result.errors.append(f"frontmatter missing required field: {fld}")
        elif not pairs[fld].strip():
            result.errors.append(f"frontmatter field '{fld}' is empty")
    if "version" in pairs and pairs["version"].strip():
        try:
            int(pairs["version"])
        except ValueError:
            result.errors.append(
                f"frontmatter 'version' must be an integer, got: {pairs['version']!r}"
            )


# ─── Body sections ────────────────────────────────────────────────────────────

def _h2_names(body: str) -> list:
    return [m.group(1).strip() for m in H2_RE.finditer(body)]


def _check_body_sections(body: str, result: ValidationResult) -> None:
    found = _h2_names(body)
    for s in REQUIRED_BODY_SECTIONS:
        if s not in found:
            result.errors.append(f"body missing required section: ## {s}")

    found_required = [n for n in found if n in REQUIRED_BODY_SECTIONS]
    expected_order = [n for n in REQUIRED_BODY_SECTIONS if n in found]
    if found_required != expected_order:
        result.errors.append(
            f"body sections out of order: got {found_required}, expected {expected_order}"
        )


def _check_business_logic_subsections(body: str, result: ValidationResult) -> None:
    bl = _section_body(body, "Business Logic")
    if bl is None:
        return
    for sub in REQUIRED_BUSINESS_LOGIC_SUBSECTIONS:
        if not re.search(rf"^###\s+{re.escape(sub)}\s*$", bl, re.MULTILINE):
            result.errors.append(f"Business Logic missing subsection: ### {sub}")


def _section_body(body: str, section: str):
    pattern = rf"^##\s+{re.escape(section)}\s*$\n?(.*?)(?=^##\s+|\Z)"
    m = re.search(pattern, body, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else None


def _subsection_body(body: str, parent: str, child: str):
    parent_body = _section_body(body, parent)
    if parent_body is None:
        return None
    pattern = rf"^###\s+{re.escape(child)}\s*$\n?(.*?)(?=^###\s+|\Z)"
    m = re.search(pattern, parent_body, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else None


# ─── Content rules ────────────────────────────────────────────────────────────

def _check_no_java_blocks(body: str, result: ValidationResult) -> None:
    """Catch both ```java fences (explicit) and untagged ``` fences whose
    content contains Java keyword markers (`public class`, `package com.x;`,
    `import java.util.List`, etc.). The Data Flow section legitimately uses
    untagged fences for ASCII trees — those won't contain these keywords."""
    seen_starts: set = set()
    for m in JAVA_FENCE_RE.finditer(body):
        line_num = body[:m.start()].count("\n") + 1
        result.errors.append(
            f"body contains a Java code block at line ~{line_num} (```java tag) — tables/prose only"
        )
        seen_starts.add(m.start())

    for m in ANY_FENCE_RE.finditer(body):
        if m.start() in seen_starts:
            continue
        tag = m.group(1).strip().lower()
        # Skip blocks with a non-empty, non-text language tag (yaml, json,
        # bash, etc. are all fine in the body — they're not Java).
        if tag and tag not in {"text", "txt", "ascii", "diff", "plain"}:
            continue
        content = m.group(2)
        if JAVA_CODE_KEYWORDS_RE.search(content):
            line_num = body[:m.start()].count("\n") + 1
            result.errors.append(
                f"body contains a Java code block at line ~{line_num} (untagged fence with Java keywords) — tables/prose only"
            )


def _check_no_placeholder_content(body: str, result: ValidationResult) -> None:
    """Sections that hold only a placeholder string (`N/A`, `TBD`, `TODO`,
    `PLACEHOLDER`, `XXX`, `---`, etc.) violate the literal-string rule:
    AGENT.md says empty sections must contain the literal 'none found',
    not a substitute. Also applies to Business Logic subsections."""
    def _check(section_name: str, body_text):
        if body_text is None:
            return
        stripped = body_text.strip().lower()
        if not stripped or stripped == NONE_FOUND:
            return
        if stripped in PLACEHOLDER_STRINGS:
            result.errors.append(
                f"section '{section_name}' contains placeholder text "
                f"({body_text.strip()!r}) — use 'none found' or fill the section"
            )

    for section in REQUIRED_BODY_SECTIONS:
        if section == "Business Logic":
            for sub in REQUIRED_BUSINESS_LOGIC_SUBSECTIONS:
                _check(sub, _subsection_body(body, "Business Logic", sub))
        else:
            _check(section, _section_body(body, section))


def _check_per_bullet_citations(body: str, result: ValidationResult) -> None:
    """Warning-level per-bullet citation check. The existing _check_citations
    is section-level (one citation in the section satisfies it). This walker
    flags specific bullet lines that have no ClassName.methodName() citation,
    which is what Codex's review called out as a false negative.

    Skips table rows ('|'-prefixed) and template hints ('['-prefixed) since
    those have legitimate non-citation formats."""
    for section in CITATION_REQUIRED_SECTIONS:
        if section in REQUIRED_BUSINESS_LOGIC_SUBSECTIONS:
            sb = _subsection_body(body, "Business Logic", section)
        else:
            sb = _section_body(body, section)
        if sb is None:
            continue
        text = sb.strip()
        if not text or text.lower() == NONE_FOUND:
            continue
        for m in BULLET_RE.finditer(sb):
            bullet = m.group(1).strip()
            if not bullet:
                continue
            if bullet.startswith("|") or bullet.startswith("["):
                continue
            if CITATION_RE.search(bullet):
                continue
            preview = bullet if len(bullet) <= 70 else bullet[:67] + "..."
            result.warnings.append(
                f"section '{section}' has a bullet without ClassName.method() citation: \"{preview}\""
            )


def _check_none_found_for_empty(body: str, result: ValidationResult) -> None:
    """Empty H2 sections — and empty Business Logic subsections — must contain the literal 'none found'."""
    for section in REQUIRED_BODY_SECTIONS:
        if section == "Business Logic":
            for sub in REQUIRED_BUSINESS_LOGIC_SUBSECTIONS:
                sb = _subsection_body(body, "Business Logic", sub)
                if sb is None:
                    continue
                if not sb.strip():
                    result.errors.append(
                        f"subsection '{sub}' under Business Logic is empty — write 'none found' if there is no content"
                    )
        else:
            sb = _section_body(body, section)
            if sb is None:
                continue
            if not sb.strip():
                result.errors.append(
                    f"section '{section}' is empty — write the literal 'none found' if there is no content"
                )


def _check_citations(body: str, result: ValidationResult) -> None:
    for section in CITATION_REQUIRED_SECTIONS:
        if section in REQUIRED_BUSINESS_LOGIC_SUBSECTIONS:
            sb = _subsection_body(body, "Business Logic", section)
        else:
            sb = _section_body(body, section)
        if sb is None:
            continue
        text = sb.strip()
        if not text or text.lower() == NONE_FOUND:
            continue
        if not CITATION_RE.search(text):
            result.warnings.append(
                f"section '{section}' has content but no ClassName.methodName() citation"
            )
