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


MAX_CHARS_PER_CHUNK = 24_000   # ~6000 tokens × 4 chars/token; truncate above this


def _collect_source_blob(domain: dict, repo_root: Path, index: dict) -> str:
    """Walk the domain's referenced classes/files and concatenate the source.

    Strategy: take every Java class whose class_name appears in the domain's
    `classes` list, plus every XML/SQL/shell file the planner attributed to the
    domain. Cap each individual file at 40KB to avoid one runaway file eating
    the whole budget."""
    parts: list[str] = []
    domain_classes = {c.split(".")[0] for c in (domain.get("classes") or [])}

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

    return "\n".join(parts)


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
                     only_domains: list | None = None) -> dict:
    """Read one response file per domain and write SKILL.md files.

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
