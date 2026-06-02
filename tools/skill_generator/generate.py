"""
Stage 3 — Generate. Host-agent execution (no API calls).

For each domain in the plan, the tool writes one prompt file containing the
full source blob for that domain. The developer pastes each prompt into their
host agent session (Claude Code, Codex, Copilot Chat, Cowork) and saves the
response as `<domain-id>.md` in the responses directory. The tool then reads
each response and writes the canonical SKILL.md.

Usage (from CLI):
    skill-gen generate-emit <plan.json> --repo <repo-root> \\
        --output-dir .skill-gen/.generate-prompts/
    # developer feeds each prompt to their AI session,
    # saves each response as .skill-gen/.generate-responses/<domain-id>.md
    skill-gen generate-ingest <plan.json> --repo <repo-root>
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

from .prompts import STAGE_3_GENERATE_PROMPT
from .validate import validate


MAX_CHARS_PER_CHUNK = 24_000   # ~6000 tokens × 4 chars/token; truncate above this


def _collect_source_blob(domain: dict, repo_root: Path, index: dict) -> str:
    """Walk the domain's referenced classes/files and concatenate the source.

    Strategy: take every Java class whose class_name appears in the domain's
    `classes` list, plus every XML/SQL/shell file the planner attributed to the
    domain. Cap each individual file at 40KB to avoid one runaway file eating
    the whole budget."""
    parts: list[str] = []
    # sorted() makes file order deterministic across Python invocations.
    # Without it, PYTHONHASHSEED randomises set iteration so domains near the
    # 24KB truncation boundary include different files on different runs.
    domain_classes = sorted({c.split(".")[-1] for c in (domain.get("classes") or [])})

    java_by_class: dict = {}
    for jc in index.get("java_classes", []):
        java_by_class.setdefault(jc["class_name"], []).append(jc)

    seen_files = set()
    for cls in domain_classes:
        for jc in java_by_class.get(cls, []):
            fp = jc["file_path"]
            if fp in seen_files:
                continue
            seen_files.add(fp)
            content = _safe_read(repo_root / fp, cap=40_000)
            if content:
                parts.append(f"--- FILE: {fp} ---\n{content}\n")

    for xml_ref in (domain.get("xmlSources") or []):
        fp = xml_ref.split(":")[0].strip()
        if fp and fp not in seen_files:
            seen_files.add(fp)
            content = _safe_read(repo_root / fp, cap=20_000)
            if content:
                parts.append(f"--- FILE: {fp} ---\n{content}\n")

    for refs_key in ("sqlSources", "shellSources"):
        for ref in (domain.get(refs_key) or []):
            fp = ref.split(":")[0].strip()
            if fp and fp not in seen_files:
                seen_files.add(fp)
                content = _safe_read(repo_root / fp, cap=20_000)
                if content:
                    parts.append(f"--- FILE: {fp} ---\n{content}\n")

    config_blob = _collect_config_pairs(domain, repo_root, index)
    if config_blob:
        parts.append(config_blob)

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Config value extraction (Stage 3)
#
# The planner attributes config-key prefixes to each domain via the `configKeys`
# field (e.g. ["app.file-delivery.*", "spring.datasource.*"]). The crawler's
# index already knows which file each prefix lives in (via `config_signals`).
# Here we close the loop: read the actual files at generate-time and extract
# the matching key:value pairs. Without this, the AI sees that the domain has
# config-driven behavior but cannot see what the values are.
# ─────────────────────────────────────────────────────────────────────────────


CONFIG_FILE_CAP = 10_000   # per-file cap for config reading


def _collect_config_pairs(domain: dict, repo_root: Path, index: dict) -> str:
    """Read config files relevant to the domain and extract matching key:value
    pairs. Returns a single blob (possibly empty) suitable for appending to
    the source blob."""
    config_keys = domain.get("configKeys") or []
    if not config_keys:
        return ""

    # Normalize prefixes: 'app.file-delivery.*' -> 'app.file-delivery'
    prefixes = [k.rstrip("*").rstrip(".") for k in config_keys if k.strip()]
    prefixes = [p for p in prefixes if p]
    if not prefixes:
        return ""

    relevant_files: dict = {}   # file_path -> config_type
    for cs in index.get("config_signals", []):
        kps = cs.get("key_prefixes") or []
        if any(_prefix_overlaps(kp, prefixes) for kp in kps):
            relevant_files[cs["file_path"]] = cs.get("config_type", "")

    parts: list = []
    for fp in sorted(relevant_files):
        ctype = relevant_files[fp]
        text = _safe_read(repo_root / fp, cap=CONFIG_FILE_CAP)
        if not text:
            continue
        if ctype == "yaml":
            pairs = _extract_matching_yaml_pairs(text, prefixes)
        else:
            pairs = _extract_matching_properties_pairs(text, prefixes)
        if pairs:
            parts.append(f"--- CONFIG: {fp} ---\n" + "\n".join(pairs) + "\n")
    return "\n".join(parts)


def _prefix_overlaps(prefix_in_file: str, domain_prefixes: list) -> bool:
    """Return True if a key prefix found in a file overlaps with any of the
    domain's requested prefixes — in either direction. This is intentionally
    forgiving so that 'spring.datasource' in a file matches both
    'spring.datasource' and 'spring' coming from the plan, and 'datasource'
    from the plan matches a file's 'spring.datasource' too."""
    for dp in domain_prefixes:
        if prefix_in_file == dp:
            return True
        if prefix_in_file.startswith(dp + "."):
            return True
        if dp.startswith(prefix_in_file + "."):
            return True
    return False


def _extract_matching_properties_pairs(text: str, prefixes: list) -> list:
    """Pull key=value or key:value lines whose key starts with any prefix.
    Preserves the original line so values keep their formatting."""
    matches: list = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        sep_index = -1
        for sep in ("=", ":"):
            i = line.find(sep)
            if i > 0 and (sep_index == -1 or i < sep_index):
                sep_index = i
        if sep_index <= 0:
            continue
        key = line[:sep_index].strip()
        if not key:
            continue
        if any(key == p or key.startswith(p + ".") for p in prefixes):
            matches.append(line)
    return matches


def _extract_matching_yaml_pairs(text: str, prefixes: list) -> list:
    """Reconstruct dotted YAML paths from indentation and emit 'path: value'
    for every leaf whose dotted path starts with any of `prefixes`. Sections
    with no inline value (just 'key:' followed by children) are skipped at
    the parent level — leaves carry the values."""
    import re as _re
    matches: list = []
    stack: list = []   # [(indent, key)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if ":" not in stripped:
            continue
        key_part, _, value_part = stripped.partition(":")
        key = key_part.strip()
        value = value_part.strip()
        if not key or not _re.match(r"^[A-Za-z_][\w.-]*$", key):
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = ".".join(k for _, k in stack + [(indent, key)])
        if value and any(path == p or path.startswith(p + ".") for p in prefixes):
            matches.append(f"{path}: {value}")
        stack.append((indent, key))
    return matches


def _safe_read(path: Path, cap: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) > cap:
        return text[:cap] + f"\n... [truncated; original was {len(text)} chars] ...\n"
    return text


def _build_prompt(domain: dict, source_blob: str) -> str:
    if len(source_blob) > MAX_CHARS_PER_CHUNK:
        source_blob = (source_blob[:MAX_CHARS_PER_CHUNK]
                       + f"\n\n... [truncated; total source was {len(source_blob)} chars; "
                       f"feature is unusually large — consider splitting the domain]\n")
    return (
        STAGE_3_GENERATE_PROMPT
        .replace("{DOMAIN_ID}", domain["id"])
        .replace("{DOMAIN_NAME}", domain.get("name", domain["id"]))
        .replace("{DOMAIN_DESCRIPTION}", domain.get("description", ""))
        .replace("{TODAY}", date.today().isoformat())
        .replace("{SOURCE_BLOB}", source_blob)
    )


def emit_prompts(plan_path: str | Path, repo_root: str | Path,
                 index_path: str | Path | None = None,
                 prompts_dir: str | Path | None = None,
                 *, only_domains: list | None = None) -> dict:
    """Write one prompt file per domain.

    Returns {"written": [paths], "skipped": [domain_ids], "failed": [{...}]}.
    """
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    repo_root = Path(repo_root).resolve()
    output_dir = Path(prompts_dir or (repo_root / ".skill-gen" / ".generate-prompts"))
    output_dir.mkdir(parents=True, exist_ok=True)

    if index_path is None:
        index_path = repo_root / ".skill-gen" / ".index.json"
    index = json.loads(Path(index_path).read_text(encoding="utf-8"))

    written, skipped, failed = [], [], []

    for i, domain in enumerate(plan.get("domains", []), start=1):
        did = domain["id"]
        if only_domains and did not in only_domains:
            continue
        source_blob = _collect_source_blob(domain, repo_root, index)
        if not source_blob.strip():
            print(f"[generate-emit] [{i}] {did}: no source found, skipping",
                  file=sys.stderr)
            failed.append({"domain": did, "reason": "no source files matched"})
            continue
        prompt = _build_prompt(domain, source_blob)
        target = output_dir / f"{did}.md"
        target.write_text(prompt, encoding="utf-8")
        written.append(str(target))
        print(f"[generate-emit] [{i}] {did}: wrote {target} "
              f"({len(prompt)} chars, source {len(source_blob)} chars)",
              file=sys.stderr)

    return {"written": written, "skipped": skipped, "failed": failed}


def ingest_responses(plan_path: str | Path, repo_root: str | Path,
                     responses_dir: str | Path | None = None,
                     output_dir: str | Path | None = None,
                     *, force_regen: bool = False,
                     only_domains: list | None = None,
                     validate_schema: bool = True) -> dict:
    """Read one response file per domain and write SKILL.md files.

    With validate_schema=True (default), each response is checked against the
    artifact-3 contract before being written. Failed responses are NOT written;
    the dev must fix the response file and re-run.

    Returns {"written": [paths], "skipped": [...], "failed": [...]}."""
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    repo_root = Path(repo_root).resolve()
    responses_dir = Path(responses_dir or (repo_root / ".skill-gen" / ".generate-responses"))
    output_dir = Path(output_dir or (repo_root / ".github" / "skills"))

    written, skipped, failed = [], [], []

    for i, domain in enumerate(plan.get("domains", []), start=1):
        did = domain["id"]
        if only_domains and did not in only_domains:
            continue
        target = output_dir / did / "SKILL.md"
        if target.exists() and not force_regen:
            print(f"[generate-ingest] [{i}] {did}: SKILL.md exists, skipping "
                  f"(use --force)", file=sys.stderr)
            skipped.append(did)
            continue
        response_path = responses_dir / f"{did}.md"
        if not response_path.exists():
            print(f"[generate-ingest] [{i}] {did}: no response file at "
                  f"{response_path}, skipping", file=sys.stderr)
            failed.append({"domain": did, "reason": "response file missing"})
            continue
        content = _strip_markdown_fence(response_path.read_text(encoding="utf-8"))
        if not content.strip():
            failed.append({"domain": did, "reason": "response file is empty"})
            continue
        if validate_schema:
            vres = validate(content, path=str(response_path))
            for w in vres.warnings:
                print(f"[generate-ingest] [{i}] {did}: WARN: {w}", file=sys.stderr)
            if not vres.ok:
                print(f"[generate-ingest] [{i}] {did}: SKILL.md validation FAILED, "
                      f"NOT writing — fix {response_path} and re-run:",
                      file=sys.stderr)
                for e in vres.errors:
                    print(f"  ERROR: {e}", file=sys.stderr)
                failed.append({"domain": did, "reason": "validation failed",
                               "errors": vres.errors})
                continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(str(target))
        print(f"[generate-ingest] [{i}] {did}: wrote {target} ({len(content)} chars)",
              file=sys.stderr)

    return {"written": written, "skipped": skipped, "failed": failed}


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text
