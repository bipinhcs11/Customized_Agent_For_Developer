"""
Stage 2 — Plan. One AI call.

Takes a CrawlIndex JSON file (output of Stage 1) and sends it to Claude with the
grouping rules. Parses the JSON response into a plan structure. Writes the plan
to <output_dir>/.plan.json for human review before Stage 3 runs.

Usage (from CLI):
    skill-gen plan <index.json> --output .github/skills/.plan.json
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

from .claude_client import ClaudeClient, ClaudeAPIError
from .prompts import STAGE_2_PLAN_PROMPT


@dataclass
class DomainGroup:
    id: str
    name: str
    description: str
    classes: list = field(default_factory=list)
    xmlSources: list = field(default_factory=list)
    sqlSources: list = field(default_factory=list)
    shellSources: list = field(default_factory=list)
    configKeys: list = field(default_factory=list)
    confidence: str = "MEDIUM"
    isGodClassSplit: bool = False
    godClassParent: str | None = None
    flags: list = field(default_factory=list)
    estimatedTokens: int = 0


@dataclass
class Plan:
    projectType: str
    framework: str
    buildSystem: str
    javaVersion: str
    warnings: list
    domains: list  # list[DomainGroup]


def _slim_index_for_planning(index: dict) -> dict:
    """The Plan stage doesn't need full method names or import lists — those are
    Stage 3 inputs. Strip the index down to package + class + annotations +
    flags to keep the prompt small."""
    slim = {
        "scan": index.get("scan", {}),
        "stats": index.get("stats", {}),
        "java_classes": [
            {
                "file_path": jc["file_path"],
                "package": jc.get("package"),
                "class_name": jc["class_name"],
                "type": jc["type"],
                "annotations": jc.get("annotations", []),
                "extends": jc.get("extends"),
                "implements": jc.get("implements", []),
                "line_count": jc.get("line_count", 0),
                "flags": jc.get("flags", []),
            }
            for jc in index.get("java_classes", [])
        ],
        "xml_signals": index.get("xml_signals", []),
        "config_signals": [
            {
                "file_path": cs["file_path"],
                "config_type": cs["config_type"],
                "key_prefixes": cs.get("key_prefixes", []),
            }
            for cs in index.get("config_signals", [])
        ],
        "sql_signals": index.get("sql_signals", []),
        "shell_signals": index.get("shell_signals", []),
    }
    return slim


def run(index_path: str | Path, output_path: str | Path | None = None,
        *, dry_run: bool = False, model: str | None = None) -> Plan:
    """Run Stage 2. Returns the parsed Plan. If output_path is given, also
    writes the raw JSON to disk so a human can review it."""
    index = json.loads(Path(index_path).read_text(encoding="utf-8"))
    slim = _slim_index_for_planning(index)
    prompt = STAGE_2_PLAN_PROMPT.replace("{INDEX_JSON}", json.dumps(slim, indent=2))

    client_kwargs = {"dry_run": dry_run}
    if model:
        client_kwargs["model"] = model
    client = ClaudeClient(**client_kwargs)

    print(f"[plan] sending {len(prompt)} chars to Claude...", file=sys.stderr)
    raw = client.complete(prompt, max_tokens=8192)
    print(f"[plan] received {len(raw)} chars", file=sys.stderr)

    plan_dict = _parse_plan_json(raw)

    plan = Plan(
        projectType=plan_dict.get("projectType", "Unknown"),
        framework=plan_dict.get("framework", "Unknown"),
        buildSystem=plan_dict.get("buildSystem", "Unknown"),
        javaVersion=plan_dict.get("javaVersion", "Unknown"),
        warnings=plan_dict.get("warnings", []),
        domains=[
            DomainGroup(
                id=d["id"],
                name=d.get("name", d["id"]),
                description=d.get("description", ""),
                classes=d.get("classes", []),
                xmlSources=d.get("xmlSources", []),
                sqlSources=d.get("sqlSources", []),
                shellSources=d.get("shellSources", []),
                configKeys=d.get("configKeys", []),
                confidence=d.get("confidence", "MEDIUM"),
                isGodClassSplit=d.get("isGodClassSplit", False),
                godClassParent=d.get("godClassParent"),
                flags=d.get("flags", []),
                estimatedTokens=d.get("estimatedTokens", 0),
            )
            for d in plan_dict.get("domains", [])
        ],
    )

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json.dumps(asdict(plan), indent=2), encoding="utf-8")
        print(f"[plan] wrote {output_path} ({len(plan.domains)} domains)", file=sys.stderr)

    return plan


def _parse_plan_json(raw: str) -> dict:
    """Tolerant JSON parser — Claude sometimes wraps JSON in code fences even
    when instructed otherwise."""
    raw = raw.strip()
    # Strip a leading ```json or ``` fence if present
    if raw.startswith("```"):
        # Drop the first line and the trailing fence
        lines = raw.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines)
    # Find the outermost JSON object
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ClaudeAPIError(f"No JSON object found in response: {raw[:500]}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ClaudeAPIError(f"Plan response was not valid JSON: {e}\n\n{raw[:1000]}")
