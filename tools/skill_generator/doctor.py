"""
skill-gen doctor — a 30-second look at a Java repo before you commit to running
the full pipeline.

The intended moment: a developer has heard about skill-gen, wants to try it on
their own messy monolith, but isn't sure if it'll work or how long it'll take.
Running this command answers both questions without writing anything to disk
and without using any AI turns. Output is plain English; pass --json for CI.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .crawler import (
    crawl,
    _detect_framework,
    _detect_build_system,
    _detect_java_version,
)


SECONDS_PER_TURN = 30   # rough paste-into-AI + save-response cycle


def diagnose(repo_path) -> dict:
    """Crawl the repo and reduce the index to a developer-facing report."""
    index = crawl(repo_path)

    java_classes = index.java_classes
    xml_signals = index.xml_signals
    config_signals = index.config_signals
    sql_signals = index.sql_signals
    shell_signals = index.shell_signals

    god_classes = [j for j in java_classes if "god_class" in (j.flags or [])]
    deprecated = [j for j in java_classes if "deprecated" in (j.flags or [])]
    tests = [j for j in java_classes if "test" in (j.flags or [])]

    # Estimate domains: distinct top-two package levels, plus a default-package
    # bucket if any default-package classes exist.
    top2_packages: set = set()
    default_package_count = 0
    for j in java_classes:
        pkg = j.package or ""
        if not pkg:
            default_package_count += 1
            continue
        top2_packages.add(".".join(pkg.split(".")[:2]))
    estimated_domains = len(top2_packages) + (1 if default_package_count else 0)

    framework = _detect_framework(java_classes, xml_signals)
    build_system = _detect_build_system(Path(repo_path))
    java_version = _detect_java_version(Path(repo_path))

    # Effort: 1 plan + N generates + 1 link
    turns = max(estimated_domains, 1) + 2
    minutes = round((turns * SECONDS_PER_TURN) / 60, 1)

    return {
        "repo_path": str(Path(repo_path).resolve()),
        "totals": {
            "java_classes": len(java_classes),
            "java_tests": len(tests),
            "xml_files": len(xml_signals),
            "config_files": len(config_signals),
            "sql_files": len(sql_signals),
            "shell_files": len(shell_signals),
        },
        "stack": {
            "framework": framework,
            "build_system": build_system,
            "java_version": java_version or "Unknown",
        },
        "estimated_domains": estimated_domains,
        "default_package_count": default_package_count,
        "god_classes": [
            {"class_name": g.class_name,
             "file_path": g.file_path,
             "lines": g.line_count}
            for g in sorted(god_classes, key=lambda x: -x.line_count)
        ],
        "deprecated_count": len(deprecated),
        "effort": {
            "host_agent_turns": turns,
            "estimated_minutes": minutes,
        },
        "warnings": index.warnings,
    }


def format_human(report: dict) -> str:
    """Plain-English version. Goal: any developer can read this in 30 seconds
    and decide whether to keep going."""
    t = report["totals"]
    s = report["stack"]
    e = report["effort"]
    god = report["god_classes"]
    repo = report["repo_path"]

    lines: list = []
    lines.append(f"== Looking at {repo} ==")
    lines.append("")

    if t["java_classes"] == 0:
        lines.append("No Java files found here. skill-gen needs a Java repo to work on.")
        lines.append("Double-check the path, or point it at a different folder.")
        return "\n".join(lines)

    lines.append(
        f"Repo: {t['java_classes']} Java classes, likely {report['estimated_domains']} feature(s)"
    )
    lines.append(
        f"Time to document: about {e['estimated_minutes']} minute(s) of paste-and-save with your AI"
    )
    lines.append("")

    # Stack section
    lines.append("What's in there")
    stack_bits = [s["framework"]]
    if s["build_system"] != "Unknown":
        stack_bits.append(f"{s['build_system']} build")
    if s["java_version"] != "Unknown":
        stack_bits.append(f"Java {s['java_version']}")
    lines.append(f"  {', '.join(stack_bits)}")
    extras = []
    if t["xml_files"]:
        extras.append(f"{t['xml_files']} XML")
    if t["config_files"]:
        extras.append(f"{t['config_files']} config")
    if t["sql_files"]:
        extras.append(f"{t['sql_files']} SQL")
    if t["shell_files"]:
        extras.append(f"{t['shell_files']} shell")
    if extras:
        lines.append(f"  Plus: {', '.join(extras)}")
    if report["default_package_count"]:
        lines.append(
            f"  {report['default_package_count']} classes in the default package "
            f"(no package declaration) — we'll group these by name prefix"
        )
    lines.append("")

    # Heads-up section (only show if there's something to flag)
    headsup: list = []
    if god:
        headsup.append("Some files are very large and will be partly truncated when we document them:")
        for g in god[:5]:
            headsup.append(f"    - {g['class_name']}  ({g['lines']} lines)")
        if len(god) > 5:
            headsup.append(f"    ...and {len(god) - 5} more")
        headsup.append("  Their docs will miss some detail. Better support for big files is coming.")
        headsup.append("")
    if report["deprecated_count"]:
        headsup.append(
            f"{report['deprecated_count']} classes are marked @Deprecated. "
            f"We'll document them and flag them so your AI knows not to extend them."
        )
        headsup.append("")
    if headsup:
        lines.append("Heads up before you start")
        for h in headsup:
            lines.append(f"  {h}" if h else h)

    # Effort breakdown
    lines.append("How long this will take you")
    lines.append(
        f"  About {e['host_agent_turns']} steps: 1 plan + "
        f"{max(report['estimated_domains'], 1)} feature(s) + 1 link pass"
    )
    lines.append(
        f"  Each step: paste a prompt into Claude or Copilot, save the response (~{SECONDS_PER_TURN}s)"
    )
    lines.append(f"  Total: about {e['estimated_minutes']} minute(s)")
    lines.append("")

    # Suggested first step
    lines.append("Suggested first step")
    lines.append("  Try ONE feature first to see if you like the output. Then commit to the rest.")
    lines.append("")
    lines.append("    skill-gen crawl . --output .skill-gen/.index.json")
    lines.append("    skill-gen plan-emit .skill-gen/.index.json")
    lines.append("    # paste the plan prompt into your AI, save the response")
    lines.append("    skill-gen plan-ingest .skill-gen/plan-response.md")
    lines.append("    # open .skill-gen/.plan.json — pick a small feature you know well")
    lines.append("    skill-gen generate-emit .skill-gen/.plan.json --repo . --only <feature-id>")
    lines.append("")
    lines.append("  Read the resulting SKILL.md. If you like it, run the full pipeline.")
    lines.append("")
    lines.append("For automation: run `skill-gen doctor --json` for machine-readable output.")

    return "\n".join(lines)


def format_json(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False, default=str)
