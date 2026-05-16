"""
Stage 3 — Generate. One AI call per approved domain, rate-limited and
checkpointed.

For each domain in the plan:
  1. Collect the full source of every class/file in the domain (Java + XML + SQL + shell).
  2. If the collected source exceeds the per-chunk budget, split at method boundaries.
  3. Send to Claude with the Stage 3 prompt. Output is a SKILL.md.
  4. Write to <repo_root>/.github/skills/<domain-id>/SKILL.md.
  5. Append the domain id to the checkpoint file so a restart can skip it.

Usage (from CLI):
    skill-gen generate <plan.json> --repo <repo-root> --output-dir .github/skills/
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .claude_client import ClaudeClient
from .prompts import STAGE_3_GENERATE_PROMPT


DEFAULT_RATE_LIMIT_DELAY_SECONDS = 2
MAX_CHARS_PER_CHUNK = 24_000   # ~6000 tokens × 4 chars/token


def _collect_source_blob(domain: dict, repo_root: Path, index: dict) -> str:
    """Walk the domain's referenced classes/files and concatenate the source.

    Strategy: take every Java class whose class_name appears in the domain's
    `classes` list, plus every XML/SQL/shell file the planner attributed to the
    domain. Cap each individual file at 40KB to avoid one runaway file eating
    the whole budget."""
    parts: list[str] = []
    domain_classes = {c.split(".")[0] for c in (domain.get("classes") or [])}

    # Index java_classes by class_name for fast lookup
    java_by_class = {}
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

    # XML files referenced
    for xml_ref in (domain.get("xmlSources") or []):
        fp = xml_ref.split(":")[0].strip()
        if fp and fp not in seen_files:
            seen_files.add(fp)
            content = _safe_read(repo_root / fp, cap=20_000)
            if content:
                parts.append(f"--- FILE: {fp} ---\n{content}\n")

    # SQL / shell sources
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


def _chunk_source(blob: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> list:
    """Split by file boundary first; if a single file is too large, split it
    at blank lines (rough method-boundary proxy)."""
    if len(blob) <= max_chars:
        return [blob]
    chunks: list = []
    current: list = []
    current_len = 0
    for file_block in re.split(r"(?=^--- FILE: )", blob, flags=re.MULTILINE):
        if not file_block.strip():
            continue
        if len(file_block) > max_chars:
            # Split this single file at blank lines
            sub_chunks = re.split(r"\n\s*\n", file_block)
            for sc in sub_chunks:
                if current_len + len(sc) > max_chars and current:
                    chunks.append("".join(current))
                    current = []
                    current_len = 0
                current.append(sc + "\n\n")
                current_len += len(sc) + 2
            continue
        if current_len + len(file_block) > max_chars and current:
            chunks.append("".join(current))
            current = []
            current_len = 0
        current.append(file_block)
        current_len += len(file_block)
    if current:
        chunks.append("".join(current))
    return chunks


def _load_checkpoint(output_dir: Path) -> dict:
    ckpt = output_dir / ".checkpoint.json"
    if ckpt.exists():
        try:
            return json.loads(ckpt.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"completed": []}
    return {"completed": []}


def _save_checkpoint(output_dir: Path, state: dict) -> None:
    ckpt = output_dir / ".checkpoint.json"
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    ckpt.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _generate_one(client: ClaudeClient, domain: dict, source_blob: str) -> str:
    """Send one or more AI calls for this domain. If chunked, the partial
    responses are returned concatenated; the caller is responsible for merging.

    To keep the v0.2 implementation simple, multi-chunk domains are sent as
    a single call with a truncation note when the blob exceeds the cap. Real
    chunk-merge can come later."""
    if len(source_blob) > MAX_CHARS_PER_CHUNK:
        source_blob = (source_blob[:MAX_CHARS_PER_CHUNK]
                       + f"\n\n... [truncated; total source was {len(source_blob)} chars; "
                       f"feature is unusually large — consider splitting the domain]\n")
    prompt = (
        STAGE_3_GENERATE_PROMPT
        .replace("{DOMAIN_ID}", domain["id"])
        .replace("{DOMAIN_NAME}", domain.get("name", domain["id"]))
        .replace("{DOMAIN_DESCRIPTION}", domain.get("description", ""))
        .replace("{TODAY}", date.today().isoformat())
        .replace("{SOURCE_BLOB}", source_blob)
    )
    return client.complete(prompt, max_tokens=4096)


def run(plan_path: str | Path, repo_root: str | Path, index_path: str | Path | None = None,
        output_dir: str | Path | None = None, *, dry_run: bool = False,
        model: str | None = None, force_regen: bool = False,
        rate_limit_delay: int = DEFAULT_RATE_LIMIT_DELAY_SECONDS,
        only_domains: list | None = None) -> dict:
    """Run Stage 3 for every domain in the plan. Returns a result dict with
    'written', 'skipped', 'failed' lists."""
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    repo_root = Path(repo_root).resolve()
    output_dir = Path(output_dir or (repo_root / ".github" / "skills"))

    # Index path defaults to <output_dir>/.index.json if not provided
    if index_path is None:
        index_path = output_dir / ".index.json"
    index = json.loads(Path(index_path).read_text(encoding="utf-8"))

    client_kwargs = {"dry_run": dry_run}
    if model:
        client_kwargs["model"] = model
    client = ClaudeClient(**client_kwargs)

    checkpoint = _load_checkpoint(output_dir)
    completed = set(checkpoint.get("completed", []))

    written, skipped, failed = [], [], []

    for i, domain in enumerate(plan.get("domains", []), start=1):
        did = domain["id"]
        if only_domains and did not in only_domains:
            continue
        target = output_dir / did / "SKILL.md"

        if did in completed and target.exists() and not force_regen:
            print(f"[generate] [{i}] {did}: already in checkpoint, skipping", file=sys.stderr)
            skipped.append(did)
            continue

        if target.exists() and not force_regen:
            print(f"[generate] [{i}] {did}: SKILL.md already exists, skipping (use --force)", file=sys.stderr)
            skipped.append(did)
            completed.add(did)
            _save_checkpoint(output_dir, {"completed": sorted(completed)})
            continue

        source_blob = _collect_source_blob(domain, repo_root, index)
        if not source_blob.strip():
            print(f"[generate] [{i}] {did}: no source found, skipping", file=sys.stderr)
            failed.append({"domain": did, "reason": "no source files matched the plan's classes"})
            continue

        print(f"[generate] [{i}] {did}: {len(source_blob)} chars of source -> Claude...", file=sys.stderr)
        try:
            content = _generate_one(client, domain, source_blob)
        except Exception as e:
            print(f"[generate] [{i}] {did}: FAILED ({type(e).__name__}: {e})", file=sys.stderr)
            failed.append({"domain": did, "reason": str(e)})
            continue

        # Strip an outer code fence if Claude added one
        content = _strip_markdown_fence(content)

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(str(target))
        completed.add(did)
        _save_checkpoint(output_dir, {"completed": sorted(completed)})
        print(f"[generate] [{i}] {did}: wrote {target} ({len(content)} chars)", file=sys.stderr)

        if i < len(plan.get("domains", [])):
            time.sleep(rate_limit_delay)

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
