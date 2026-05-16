"""
Stage 4 — Link. Host-agent execution (no API calls).

emit_prompt: collects the first ~600 chars of each generated SKILL.md plus its
domain id and writes a Stage-4 prompt asking the host agent to identify
cross-domain dependencies.

ingest_response: parses the host agent's JSON response and appends to each
affected SKILL.md's `related_skills:` frontmatter and the body's Related Skills
table.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .prompts import STAGE_4_LINK_PROMPT


class LinkParseError(RuntimeError):
    pass


def emit_prompt(skills_dir: str | Path, prompt_path: str | Path) -> Path:
    """Write the Stage-4 prompt to prompt_path."""
    skills_dir = Path(skills_dir)
    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    if not skill_files:
        print(f"[link-emit] no SKILL.md files under {skills_dir}", file=sys.stderr)
    summaries: list = []
    for sf in skill_files:
        text = sf.read_text(encoding="utf-8")
        domain_id = sf.parent.name
        head = text[:600]
        summaries.append(f"--- DOMAIN: {domain_id} ---\n{head}\n")
    prompt = STAGE_4_LINK_PROMPT.replace("{SUMMARIES}", "\n".join(summaries))
    prompt_path = Path(prompt_path)
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")
    print(f"[link-emit] wrote prompt to {prompt_path} "
          f"({len(prompt)} chars, {len(skill_files)} domains)", file=sys.stderr)
    return prompt_path


def ingest_response(response_path: str | Path,
                    skills_dir: str | Path) -> dict:
    """Parse the host agent's response and update each affected SKILL.md.

    Returns {"links": [...], "updated": [paths]}."""
    skills_dir = Path(skills_dir)
    raw = Path(response_path).read_text(encoding="utf-8")
    links = _parse_links_json(raw).get("links", [])
    print(f"[link-ingest] found {len(links)} cross-domain link(s)", file=sys.stderr)

    by_from: dict = {}
    for ln in links:
        if not isinstance(ln, dict) or "from" not in ln or "to" not in ln:
            continue
        by_from.setdefault(ln["from"], []).append(ln)

    updated: list = []
    for domain_id, domain_links in by_from.items():
        skill_path = skills_dir / domain_id / "SKILL.md"
        if not skill_path.exists():
            print(f"[link-ingest] {domain_id}: SKILL.md not found, skipping",
                  file=sys.stderr)
            continue
        text = skill_path.read_text(encoding="utf-8")
        new_text = _apply_links(text, domain_links)
        if new_text != text:
            skill_path.write_text(new_text, encoding="utf-8")
            updated.append(str(skill_path))
            print(f"[link-ingest] {domain_id}: appended {len(domain_links)} link(s)",
                  file=sys.stderr)

    return {"links": links, "updated": updated}


def _apply_links(text: str, links: list) -> str:
    """Update frontmatter `related_skills:` and the body Related Skills table."""
    targets = [ln["to"] for ln in links]
    joined = ", ".join(sorted(set(targets)))
    text = re.sub(
        r"^related_skills:\s*(?:PLACEHOLDER|none|\[PLACEHOLDER\])\s*$",
        f"related_skills: {joined}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
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
        raise LinkParseError(f"No JSON in link response: {raw[:500]}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise LinkParseError(f"Link response was not valid JSON: {e}\n\n{raw[:500]}")
