"""
Stage 2 — Plan. Host-agent execution (no API calls).

Two operations:
  emit_prompt(index_path, prompt_path)
      Read crawl-index JSON, assemble the Stage-2 prompt, write it to a file.
      The developer pastes this prompt into their host agent session
      (Claude Code, Codex, Copilot Chat, Cowork) and saves the response.

  ingest_response(response_path, plan_path)
      Read the host agent's response (JSON, optionally fenced), parse it,
      validate the shape, and write the canonical plan.json.

Usage (from CLI):
    skill-gen plan-emit <index.json> --output .skill-gen/plan-prompt.md
    # developer feeds .skill-gen/plan-prompt.md to their AI session,
    # saves the response as .skill-gen/plan-response.md
    skill-gen plan-ingest <response.md> --output .skill-gen/plan.json
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

from .prompts import STAGE_2_PLAN_PROMPT


class PlanParseError(RuntimeError):
    pass


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
    return {
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


def emit_prompt(index_path: str | Path, prompt_path: str | Path) -> Path:
    """Assemble the Stage-2 prompt and write it to prompt_path."""
    index = json.loads(Path(index_path).read_text(encoding="utf-8"))
    slim = _slim_index_for_planning(index)
    prompt = STAGE_2_PLAN_PROMPT.replace("{INDEX_JSON}", json.dumps(slim, indent=2))
    prompt_path = Path(prompt_path)
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")
    print(f"[plan-emit] wrote prompt to {prompt_path} ({len(prompt)} chars)",
          file=sys.stderr)
    return prompt_path


def ingest_response(response_path: str | Path,
                    plan_path: str | Path | None = None) -> Plan:
    """Parse a host-agent response into a Plan. Optionally persist to plan_path."""
    raw = Path(response_path).read_text(encoding="utf-8")
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
    if plan_path:
        plan_path = Path(plan_path)
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(asdict(plan), indent=2), encoding="utf-8")
        print(f"[plan-ingest] wrote {plan_path} ({len(plan.domains)} domains)",
              file=sys.stderr)
    return plan


def _parse_plan_json(raw: str) -> dict:
    """Tolerant JSON parser — host agents sometimes wrap JSON in code fences."""
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
        raise PlanParseError(f"No JSON object found in response: {raw[:500]}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise PlanParseError(f"Plan response was not valid JSON: {e}\n\n{raw[:1000]}")
