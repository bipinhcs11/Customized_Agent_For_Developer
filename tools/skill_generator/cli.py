"""
Command-line entry point for the FeatureBased Skill Generator Agent.

Subcommands:
    crawl       Stage 1 — scan a Java repo, emit index JSON (zero AI calls)
    plan        Stage 2 — group classes into domains (1 AI call)
    generate    Stage 3 — write a SKILL.md per approved domain (1 AI call per domain)
    link        Stage 4 — find cross-domain dependencies (1 AI call)
    update      Phase 2 — refresh skills affected by a git diff
    run-all     Convenience: crawl → plan → generate → link in one invocation

Every AI-dependent subcommand reads ANTHROPIC_API_KEY from the environment, or
respects --dry-run to print the prompt without sending. Use --dry-run while
iterating on prompts; use the real key for actual output.

Usage:
    skill-gen crawl <repo>                  → index.json
    skill-gen plan <index.json>             → plan.json
    skill-gen generate <plan.json> --repo <repo>
    skill-gen link <skills-dir>
    skill-gen update --feature <id>
    skill-gen run-all <repo>                → end-to-end
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .crawler import crawl, CrawlIndex, TOOL_VERSION
from . import plan as plan_mod
from . import generate as generate_mod
from . import link as link_mod
from . import update as update_mod


# ─────────────────────────────────────────────────────────────────────────────
# Crawl
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_crawl(args: argparse.Namespace) -> int:
    try:
        index: CrawlIndex = crawl(
            args.path,
            extra_excludes=set(args.exclude or []),
            include_tests=not args.skip_tests,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    out = json.dumps(
        asdict(index),
        indent=2 if not args.compact else None,
        ensure_ascii=False,
        default=str,
    )
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out)
        print(f"wrote {args.output} "
              f"({index.stats['java_classes']} java, "
              f"{index.stats['xml_files']} xml, "
              f"{index.stats['config_files']} config, "
              f"{index.stats.get('sql_files', 0)} sql, "
              f"{index.stats.get('shell_files', 0)} shell)",
              file=sys.stderr)
    else:
        print(out)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Plan
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_plan(args: argparse.Namespace) -> int:
    try:
        plan = plan_mod.run(
            args.index,
            args.output,
            dry_run=args.dry_run,
            model=args.model,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not args.output:
        print(json.dumps(asdict(plan), indent=2))
    else:
        print(f"plan: {len(plan.domains)} domains "
              f"(framework={plan.framework}, project_type={plan.projectType})",
              file=sys.stderr)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Generate
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_generate(args: argparse.Namespace) -> int:
    try:
        result = generate_mod.run(
            args.plan,
            args.repo,
            index_path=args.index,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            model=args.model,
            force_regen=args.force,
            only_domains=args.only or None,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"\ngenerate: wrote {len(result['written'])} skill(s), "
          f"skipped {len(result['skipped'])}, "
          f"failed {len(result['failed'])}",
          file=sys.stderr)
    if result["failed"]:
        for f in result["failed"]:
            print(f"  FAILED: {f}", file=sys.stderr)
        return 2
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Link
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_link(args: argparse.Namespace) -> int:
    try:
        result = link_mod.run(
            args.skills_dir,
            dry_run=args.dry_run,
            model=args.model,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"link: found {len(result['links'])} link(s), updated {len(result['updated'])} file(s)",
          file=sys.stderr)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Update (Phase 2)
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_update(args: argparse.Namespace) -> int:
    try:
        result = update_mod.run(
            args.repo,
            base=args.base,
            head=args.head,
            feature=args.feature,
            dry_run=args.dry_run,
            model=args.model,
            commit=args.commit,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"update: refreshed {len(result.get('updated', []))} skill(s)", file=sys.stderr)
    if result.get("failed"):
        for f in result["failed"]:
            print(f"  FAILED: {f}", file=sys.stderr)
        return 2
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Run-all (convenience)
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_run_all(args: argparse.Namespace) -> int:
    repo = Path(args.path).resolve()
    output_dir = Path(args.output_dir or (repo / ".github" / "skills")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / ".index.json"
    plan_path = output_dir / ".plan.json"

    print(f"\n=== Stage 1: Crawl ===", file=sys.stderr)
    args.output = str(index_path)
    args.exclude = []
    args.skip_tests = False
    args.compact = False
    args.path = str(repo)
    rc = _cmd_crawl(args)
    if rc != 0:
        return rc

    print(f"\n=== Stage 2: Plan ===", file=sys.stderr)
    args.index = str(index_path)
    args.output = str(plan_path)
    rc = _cmd_plan(args)
    if rc != 0:
        return rc

    print(f"\n=== Stage 3: Generate ===", file=sys.stderr)
    args.plan = str(plan_path)
    args.repo = str(repo)
    args.index = str(index_path)
    args.output_dir = str(output_dir)
    args.force = False
    args.only = None
    rc = _cmd_generate(args)
    if rc != 0:
        return rc

    print(f"\n=== Stage 4: Link ===", file=sys.stderr)
    args.skills_dir = str(output_dir)
    rc = _cmd_link(args)
    return rc


# ─────────────────────────────────────────────────────────────────────────────
# Argparse wiring
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill-gen",
        description="FeatureBased Skill Generator Agent — Java repo → SKILL.md per feature.",
    )
    parser.add_argument("--version", action="version", version=f"skill-gen {TOOL_VERSION}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # crawl
    p = sub.add_parser("crawl", help="Stage 1: scan a Java repo, emit index JSON (zero AI calls)")
    p.add_argument("path", help="Path to the Java repo root")
    p.add_argument("--output", "-o", help="Write JSON to this file instead of stdout")
    p.add_argument("--exclude", action="append", default=[],
                   help="Additional directory name to exclude (repeatable)")
    p.add_argument("--skip-tests", action="store_true",
                   help="Exclude *Test.java / *Tests.java / */test/* entirely")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=_cmd_crawl)

    # plan
    p = sub.add_parser("plan", help="Stage 2: group classes into business domains (1 AI call)")
    p.add_argument("index", help="Path to the index.json produced by crawl")
    p.add_argument("--output", "-o", help="Write plan to this file (default: stdout)")
    p.add_argument("--dry-run", action="store_true", help="Print the prompt; don't call Claude")
    p.add_argument("--model", help="Override the default Claude model")
    p.set_defaults(func=_cmd_plan)

    # generate
    p = sub.add_parser("generate", help="Stage 3: write a SKILL.md per approved domain")
    p.add_argument("plan", help="Path to the plan.json produced by plan")
    p.add_argument("--repo", required=True, help="Repo root (used to read source files)")
    p.add_argument("--index", help="Index JSON path (default: <output-dir>/.index.json)")
    p.add_argument("--output-dir", help="Where to write SKILL.mds (default: <repo>/.github/skills/)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--model", help="Override the default Claude model")
    p.add_argument("--force", action="store_true", help="Regenerate even if SKILL.md exists")
    p.add_argument("--only", action="append", default=[],
                   help="Only generate this domain id (repeatable)")
    p.set_defaults(func=_cmd_generate)

    # link
    p = sub.add_parser("link", help="Stage 4: append cross-domain relationships to each SKILL.md")
    p.add_argument("skills_dir", help="Path to the skills directory (e.g., .github/skills)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--model", help="Override the default Claude model")
    p.set_defaults(func=_cmd_link)

    # update
    p = sub.add_parser("update", help="Phase 2: refresh skills for features affected by a git diff")
    p.add_argument("--repo", default=".", help="Repo root (default: current dir)")
    p.add_argument("--base", default="HEAD~1", help="git diff base (default: HEAD~1)")
    p.add_argument("--head", default="HEAD", help="git diff head (default: HEAD)")
    p.add_argument("--feature", help="Force update of a specific feature id (skip git diff)")
    p.add_argument("--commit", action="store_true",
                   help="git-add and commit the updated SKILL.mds with auto message")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--model", help="Override the default Claude model")
    p.set_defaults(func=_cmd_update)

    # run-all
    p = sub.add_parser("run-all", help="Convenience: crawl → plan → generate → link end-to-end")
    p.add_argument("path", help="Path to the Java repo root")
    p.add_argument("--output-dir", help="Where to write artifacts (default: <repo>/.github/skills/)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--model", help="Override the default Claude model")
    p.set_defaults(func=_cmd_run_all)

    # generate-all (multi-repo, not yet implemented)
    p = sub.add_parser("generate-all",
                       help="Multi-repo orchestration via agent-config.yml (NOT IMPLEMENTED)")
    p.set_defaults(func=lambda a: (print("not implemented", file=sys.stderr) or 64))

    return parser


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
