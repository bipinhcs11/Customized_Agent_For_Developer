"""
Command-line entry point for the FeatureBased Skill Generator Agent.

The tool is host-agent-driven: every LLM-dependent stage has two halves —
`*-emit` writes a prompt file, `*-ingest` reads the response saved by the
developer's AI session (Claude Code, Codex, Copilot Chat, Cowork). Zero
outbound network calls are ever made.

Subcommands:
    crawl              Stage 1 — scan a Java repo, write index JSON
    plan-emit          Stage 2 — write the planning prompt
    plan-ingest        Stage 2 — turn the response into plan.json
    generate-emit      Stage 3 — write one prompt per domain
    generate-ingest    Stage 3 — turn each response into SKILL.md
    link-emit          Stage 4 — write the cross-domain link prompt
    link-ingest        Stage 4 — apply links to each SKILL.md
    update-emit        Phase 2 — write update prompts for changed features
    update-ingest      Phase 2 — apply updates to each SKILL.md

Default file layout (relative to a target repo):
    .skill-gen/.index.json
    .skill-gen/plan-prompt.md            (emit)
    .skill-gen/plan-response.md          (developer fills this in)
    .skill-gen/.plan.json
    .skill-gen/.generate-prompts/<domain-id>.md     (emit, one per domain)
    .skill-gen/.generate-responses/<domain-id>.md   (developer fills these in)
    .github/skills/<domain-id>/SKILL.md             (final output)
    .skill-gen/link-prompt.md            (emit)
    .skill-gen/link-response.md          (developer fills)
    .skill-gen/.update-prompts/<feature-id>.md
    .skill-gen/.update-responses/<feature-id>.md
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
from . import validate as validate_mod


def _default_workdir(repo_or_index: str | Path) -> Path:
    """Pick a sensible default `.skill-gen/` directory."""
    p = Path(repo_or_index).resolve()
    if p.is_file():
        p = p.parent
    if p.name == ".skill-gen":
        return p
    return p / ".skill-gen"


# ─── Crawl ────────────────────────────────────────────────────────────────────

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


# ─── Plan ─────────────────────────────────────────────────────────────────────

def _cmd_plan_emit(args: argparse.Namespace) -> int:
    output = args.output or (_default_workdir(args.index) / "plan-prompt.md")
    try:
        path = plan_mod.emit_prompt(args.index, output)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    response_hint = Path(output).parent / "plan-response.md"
    print(f"\nNext step: paste the contents of {path} into your AI session "
          f"(Claude Code / Codex / Copilot Chat / Cowork).\n"
          f"Save the response as {response_hint}, then run:\n"
          f"  skill-gen plan-ingest {response_hint}",
          file=sys.stderr)
    return 0


def _cmd_plan_ingest(args: argparse.Namespace) -> int:
    output = args.output or (Path(args.response).parent / ".plan.json")
    try:
        plan_mod.ingest_response(args.response, output)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


# ─── Generate ─────────────────────────────────────────────────────────────────

def _cmd_generate_emit(args: argparse.Namespace) -> int:
    try:
        result = generate_mod.emit_prompts(
            args.plan, args.repo,
            index_path=args.index,
            prompts_dir=args.prompts_dir,
            only_domains=args.only or None,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    prompts_dir = args.prompts_dir or str(Path(args.repo).resolve() / ".skill-gen" / ".generate-prompts")
    responses_dir = str(Path(prompts_dir).parent / ".generate-responses")
    print(f"\ngenerate-emit: wrote {len(result['written'])} prompt(s)",
          file=sys.stderr)
    if result["failed"]:
        for f in result["failed"]:
            print(f"  FAILED: {f}", file=sys.stderr)
    print(f"\nNext step: for each prompt under {prompts_dir}, paste it into your "
          f"AI session and save the response as {responses_dir}/<domain-id>.md. "
          f"Then run:\n  skill-gen generate-ingest {args.plan} --repo {args.repo}",
          file=sys.stderr)
    return 0


def _cmd_generate_ingest(args: argparse.Namespace) -> int:
    try:
        result = generate_mod.ingest_responses(
            args.plan, args.repo,
            responses_dir=args.responses_dir,
            output_dir=args.output_dir,
            force_regen=args.force,
            only_domains=args.only or None,
            validate_schema=not args.no_validate,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"\ngenerate-ingest: wrote {len(result['written'])} skill(s), "
          f"skipped {len(result['skipped'])}, "
          f"failed {len(result['failed'])}", file=sys.stderr)
    if result["failed"]:
        for f in result["failed"]:
            print(f"  FAILED: {f}", file=sys.stderr)
        return 2
    return 0


# ─── Link ─────────────────────────────────────────────────────────────────────

def _cmd_link_emit(args: argparse.Namespace) -> int:
    output = args.output or (Path(args.skills_dir).parent / ".skill-gen" / "link-prompt.md")
    try:
        path = link_mod.emit_prompt(args.skills_dir, output)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    response_hint = Path(output).parent / "link-response.md"
    print(f"\nNext step: paste {path} into your AI session, save the response as "
          f"{response_hint}, then run:\n"
          f"  skill-gen link-ingest {response_hint} --skills-dir {args.skills_dir}",
          file=sys.stderr)
    return 0


def _cmd_link_ingest(args: argparse.Namespace) -> int:
    try:
        result = link_mod.ingest_response(
            args.response, args.skills_dir,
            validate_schema=not args.no_validate,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"link-ingest: applied {len(result['links'])} link(s), "
          f"updated {len(result['updated'])} file(s)", file=sys.stderr)
    return 0


# ─── Update (Phase 2) ─────────────────────────────────────────────────────────

def _cmd_update_emit(args: argparse.Namespace) -> int:
    try:
        result = update_mod.emit_prompts(
            args.repo,
            base=args.base, head=args.head,
            feature=args.feature,
            prompts_dir=args.prompts_dir,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"update-emit: wrote {len(result['written'])} prompt(s), "
          f"failed {len(result['failed'])}", file=sys.stderr)
    if result["written"]:
        responses_dir = args.prompts_dir
        if responses_dir is None:
            responses_dir = str(Path(args.repo).resolve() / ".skill-gen" / ".update-responses")
        else:
            responses_dir = str(Path(responses_dir).parent / ".update-responses")
        print(f"\nNext step: feed each prompt to your AI session and save the "
              f"response as {responses_dir}/<feature-id>.md. Then run:\n"
              f"  skill-gen update-ingest --repo {args.repo}",
              file=sys.stderr)
    return 0


def _cmd_update_ingest(args: argparse.Namespace) -> int:
    try:
        result = update_mod.ingest_responses(
            args.repo,
            responses_dir=args.responses_dir,
            commit=args.commit,
            feature=args.feature,
            validate_schema=not args.no_validate,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"update-ingest: refreshed {len(result.get('updated', []))} skill(s)",
          file=sys.stderr)
    if result.get("failed"):
        for f in result["failed"]:
            print(f"  FAILED: {f}", file=sys.stderr)
        return 2
    return 0


# ─── Argparse wiring ──────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill-gen",
        description="FeatureBased Skill Generator — host-agent-driven, "
                    "zero outbound API calls.",
    )
    parser.add_argument("--version", action="version", version=f"skill-gen {TOOL_VERSION}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # crawl
    p = sub.add_parser("crawl", help="Stage 1: scan a Java repo, emit index JSON")
    p.add_argument("path", help="Path to the Java repo root")
    p.add_argument("--output", "-o", help="Write JSON to this file instead of stdout")
    p.add_argument("--exclude", action="append", default=[],
                   help="Additional directory name to exclude (repeatable)")
    p.add_argument("--skip-tests", action="store_true",
                   help="Exclude *Test.java / *Tests.java / */test/* entirely")
    p.add_argument("--compact", action="store_true", help="Single-line JSON output")
    p.set_defaults(func=_cmd_crawl)

    # plan-emit
    p = sub.add_parser("plan-emit",
                       help="Stage 2: write the planning prompt for the host agent")
    p.add_argument("index", help="Path to the index.json produced by crawl")
    p.add_argument("--output", "-o", help="Where to write the prompt "
                   "(default: <index-dir>/.skill-gen/plan-prompt.md)")
    p.set_defaults(func=_cmd_plan_emit)

    # plan-ingest
    p = sub.add_parser("plan-ingest",
                       help="Stage 2: turn the host agent's response into plan.json")
    p.add_argument("response", help="Path to the response file (markdown or raw JSON)")
    p.add_argument("--output", "-o", help="Where to write plan.json "
                   "(default: alongside the response file)")
    p.set_defaults(func=_cmd_plan_ingest)

    # generate-emit
    p = sub.add_parser("generate-emit",
                       help="Stage 3: write one prompt per approved domain")
    p.add_argument("plan", help="Path to plan.json")
    p.add_argument("--repo", required=True, help="Repo root (for reading source files)")
    p.add_argument("--index", help="Index JSON path "
                   "(default: <repo>/.skill-gen/.index.json)")
    p.add_argument("--prompts-dir", help="Where to write per-domain prompts "
                   "(default: <repo>/.skill-gen/.generate-prompts/)")
    p.add_argument("--only", action="append", default=[],
                   help="Only emit this domain id (repeatable)")
    p.set_defaults(func=_cmd_generate_emit)

    # generate-ingest
    p = sub.add_parser("generate-ingest",
                       help="Stage 3: turn per-domain responses into SKILL.md files")
    p.add_argument("plan", help="Path to plan.json")
    p.add_argument("--repo", required=True, help="Repo root")
    p.add_argument("--responses-dir", help="Where the per-domain responses live "
                   "(default: <repo>/.skill-gen/.generate-responses/)")
    p.add_argument("--output-dir", help="Where to write SKILL.mds "
                   "(default: <repo>/.github/skills/)")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing SKILL.md files")
    p.add_argument("--only", action="append", default=[],
                   help="Only ingest this domain id (repeatable)")
    p.add_argument("--no-validate", action="store_true",
                   help="Skip artifact-3 schema validation (not recommended)")
    p.set_defaults(func=_cmd_generate_ingest)

    # link-emit
    p = sub.add_parser("link-emit",
                       help="Stage 4: write the cross-domain link prompt")
    p.add_argument("skills_dir", help="Skills directory (e.g., .github/skills)")
    p.add_argument("--output", "-o", help="Where to write the prompt "
                   "(default: <skills-dir>/../.skill-gen/link-prompt.md)")
    p.set_defaults(func=_cmd_link_emit)

    # link-ingest
    p = sub.add_parser("link-ingest",
                       help="Stage 4: apply the host agent's link response to each SKILL.md")
    p.add_argument("response", help="Path to the link response file")
    p.add_argument("--skills-dir", required=True,
                   help="Skills directory (e.g., .github/skills)")
    p.add_argument("--no-validate", action="store_true",
                   help="Skip artifact-3 schema validation after link rewrite (not recommended)")
    p.set_defaults(func=_cmd_link_ingest)

    # update-emit
    p = sub.add_parser("update-emit",
                       help="Phase 2: write update prompts for features affected by a git diff")
    p.add_argument("--repo", default=".", help="Repo root (default: current dir)")
    p.add_argument("--base", default="HEAD~1", help="git diff base (default: HEAD~1)")
    p.add_argument("--head", default="HEAD", help="git diff head (default: HEAD)")
    p.add_argument("--feature", help="Force-emit for a specific feature id (skip git diff)")
    p.add_argument("--prompts-dir", help="Where to write prompts "
                   "(default: <repo>/.skill-gen/.update-prompts/)")
    p.set_defaults(func=_cmd_update_emit)

    # update-ingest
    p = sub.add_parser("update-ingest",
                       help="Phase 2: apply per-feature responses to each SKILL.md")
    p.add_argument("--repo", default=".", help="Repo root (default: current dir)")
    p.add_argument("--responses-dir", help="Where the per-feature responses live "
                   "(default: <repo>/.skill-gen/.update-responses/)")
    p.add_argument("--feature", help="Apply only this feature id")
    p.add_argument("--commit", action="store_true",
                   help="git-add + commit the updated SKILL.mds (auto message)")
    p.add_argument("--no-validate", action="store_true",
                   help="Skip artifact-3 schema validation (not recommended)")
    p.set_defaults(func=_cmd_update_ingest)

    # validate
    p = sub.add_parser("validate",
                       help="Validate one or more SKILL.md files against the artifact-3 contract")
    p.add_argument("paths", nargs="+",
                   help="SKILL.md file paths and/or directories (recursively scanned for SKILL.md)")
    p.set_defaults(func=_cmd_validate)

    return parser


def _cmd_validate(args: argparse.Namespace) -> int:
    results = validate_mod.validate_paths(args.paths)
    if not results:
        print("error: no SKILL.md files found at the given paths", file=sys.stderr)
        return 1
    return validate_mod.print_report(results)


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
