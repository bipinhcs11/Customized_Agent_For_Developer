"""
Stage 4 — Link. One AI call.

Reads the first ~400 chars of each generated SKILL.md, sends a summary list to
Claude, gets back cross-domain `links[]`, then appends to each affected
SKILL.md's `related_skills:` frontmatter and the body's Related Skills table.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .claude_client import ClaudeClient, ClaudeAPIError
from .prompts import STAGE_4_LINK_PROMPT


def run(skills_dir: str | Path, *, dry_run: bool = False, model: str | None = None) -> dict:
    skills_dir = Path(skills_dir)
    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    if not skill_files:
        print(f"[link] no SKILL.md files under {skills_dir}", file=sys.stderr)
        return {"links": [], "updated": []}

    summaries: list = []
    for sf in skill_files:
        text = sf.read_text(encoding="utf-8")
        domain_id = sf.parent.name
        head = text[:600]
        summaries.append(f"--- DOMAIN: {domain_id} ---\n{head}\n")

    prompt = STAGE_4_LINK_PROMPT.replace("{SUMMARIES}", "\n".join(summaries))

    client_kwargs = {"dry_run": dry_run}
    if model:
        client_kwargs["model"] = model
    client = ClaudeClient(**client_kwargs)

    print(f"[link] sending {len(prompt)} chars to Claude...", file=sys.stderr)
    raw = client.complete(prompt, max_tokens=4096)
    print(f"[link] received {len(raw)} chars", file=sys.stderr)

    links = _parse_links_json(raw).get("links", [])
    print(f"[link] found {len(links)} cross-domain links", file=sys.stderr)

    updated: list = []
    # Group links by `from` domain so we can edit each SKILL.md once
    by_from: dict = {}
    for ln in links:
        if not isinstance(ln, dict) or "from" not in ln or "to" not in ln:
            continue
        by_from.setdefault(ln["from"], []).append(ln)

    for domain_id, domain_links in by_from.items():
        skill_path = skills_dir / domain_id / "SKILL.md"
        if not skill_path.exists():
            print(f"[link] {domain_id}: SKILL.md not found, skipping", file=sys.stderr)
            continue
        text = skill_path.read_text(encoding="utf-8")
        new_text = _apply_links(text, domain_links)
        if new_text != text:
            skill_path.write_text(new_text, encoding="utf-8")
            updated.append(str(skill_path))
            print(f"[link] {domain_id}: appended {len(domain_links)} link(s)", file=sys.stderr)

    return {"links": links, "updated": updated}


def _apply_links(text: str, links: list) -> str:
    """Update frontmatter `related_skills:` and the body Related Skills table."""
    # 1) Update the frontmatter `related_skills:` line
    targets = [ln["to"] for ln in links]
    joined = ", ".join(sorted(set(targets)))
    text = re.sub(
        r"^related_skills:\s*(?:PLACEHOLDER|none|\[PLACEHOLDER\])\s*$",
        f"related_skills: {joined}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    # 2) Replace the Related Skills body section
    table_rows = "\n".join(
        f"| {ln['to']} | {ln.get('type', 'calls')} | {ln.get('reason', '')} |"
        for ln in links
    )
    new_section = (
        "## Related Skills\n"
        "| Domain | Relationship | Reason |\n"
        "|--------|-------------|--------|\n"
        f"{table_rows}\n"
    )
    text = re.sub(
        r"## Related Skills\n.*?(?=\n## )",
        new_section,
        text,
        count=1,
        flags=re.DOTALL,
    )
    return text


def _parse_links_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ClaudeAPIError(f"No JSON in link response: {raw[:500]}")
    return json.loads(match.group(0))
