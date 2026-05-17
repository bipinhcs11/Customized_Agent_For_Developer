"""
Phase 2 — Incremental updater. Host-agent execution (no API calls).

emit_prompts:
    Reads `git diff` for changed Java/XML/SQL/shell files, maps each changed
    file to a feature id by looking at existing skill folders, then re-crawls
    the repo and writes one update prompt per affected feature.

ingest_responses:
    Reads each per-feature response, bumps the `version`, writes the refreshed
    SKILL.md, and (optionally) commits the changes.

Trigger surfaces (all run the same CLI):
  - GitHub Action on PR merge (preferred)
  - Git pre-commit hook
  - File watcher
  - Manual: skill-gen update-emit --feature file-delivery
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .crawler import crawl
from .prompts import PHASE_2_UPDATE_PROMPT_PREFIX, STAGE_3_GENERATE_PROMPT
from .generate import _collect_source_blob, _strip_markdown_fence
from .validate import validate


def _git_changed_files(repo_root: Path, base: str = "HEAD~1", head: str = "HEAD") -> list:
    """Return relative file paths changed between `base` and `head`. Falls back
    to staged + unstaged if there's no `base` (e.g., shallow clone)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only", f"{base}..{head}"],
            capture_output=True, text=True, check=True,
        )
        files = [l.strip() for l in out.stdout.splitlines() if l.strip()]
        if files:
            return files
    except subprocess.CalledProcessError:
        pass
    out = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True, text=True, check=False,
    )
    return [l[3:].strip() for l in out.stdout.splitlines() if l.strip()]


def _map_files_to_features(changed_files: list, skills_dir: Path) -> dict:
    """For each existing SKILL.md, read which file paths it claims. Return
    {feature_id: [changed_files]}. Simple substring match on basenames."""
    feature_files: dict = {}
    if not skills_dir.exists():
        return feature_files

    skill_to_basenames: dict = {}
    for skill_path in skills_dir.glob("*/SKILL.md"):
        feature_id = skill_path.parent.name
        text = skill_path.read_text(encoding="utf-8")
        basenames = set(re.findall(
            r"\b([A-Za-z0-9_.-]+\.(?:java|xml|sql|sh|yml|yaml|properties))\b", text
        ))
        skill_to_basenames[feature_id] = basenames

    for f in changed_files:
        basename = Path(f).name
        matched = False
        for feature_id, basenames in skill_to_basenames.items():
            if basename in basenames:
                feature_files.setdefault(feature_id, []).append(f)
                matched = True
        if not matched:
            print(f"[update] {f}: no existing skill claims this file — "
                  f"may be a new feature; full re-plan needed", file=sys.stderr)
    return feature_files


def _resolve_skills_dir(repo_root: Path) -> Path | None:
    candidates = [repo_root / ".github" / "skills", repo_root / "skills"]
    for c in candidates:
        if c.exists():
            return c
    return None


def _domain_from_skill(skill_md: str, feature_id: str) -> dict:
    """Reconstruct a minimal domain dict from an existing SKILL.md."""
    classes = set(re.findall(r"\b([A-Z][A-Za-z0-9]+)\.java\b", skill_md))
    xml_files = re.findall(r"\b([A-Za-z0-9_./-]+\.xml)\b", skill_md)
    sql_files = re.findall(r"\b([A-Za-z0-9_./-]+\.sql)\b", skill_md)
    sh_files = re.findall(r"\b([A-Za-z0-9_./-]+\.sh)\b", skill_md)
    return {
        "id": feature_id,
        "name": feature_id,
        "description": "",
        "classes": list(classes),
        "xmlSources": [f"{x}: from prior skill" for x in xml_files],
        "sqlSources": [f"{s}: from prior skill" for s in sql_files],
        "shellSources": [f"{s}: from prior skill" for s in sh_files],
    }


def emit_prompts(repo_root: str | Path, *, base: str = "HEAD~1",
                 head: str = "HEAD", feature: str | None = None,
                 prompts_dir: str | Path | None = None) -> dict:
    """Write one update prompt per affected feature."""
    repo_root = Path(repo_root).resolve()
    skills_dir = _resolve_skills_dir(repo_root)
    if skills_dir is None:
        print(f"[update-emit] no skills/ or .github/skills/ found in {repo_root}",
              file=sys.stderr)
        return {"written": [], "skipped": [], "failed": []}

    if feature:
        feature_to_files = {feature: ["(manual trigger)"]}
    else:
        changed = _git_changed_files(repo_root, base, head)
        print(f"[update-emit] {len(changed)} files changed between {base}..{head}",
              file=sys.stderr)
        feature_to_files = _map_files_to_features(changed, skills_dir)

    if not feature_to_files:
        print("[update-emit] no features affected by these changes", file=sys.stderr)
        return {"written": [], "skipped": [], "failed": []}

    print(f"[update-emit] re-crawling {repo_root}...", file=sys.stderr)
    index = crawl(repo_root)
    index_dict = asdict(index)

    prompts_dir = Path(prompts_dir or (repo_root / ".skill-gen" / ".update-prompts"))
    prompts_dir.mkdir(parents=True, exist_ok=True)

    written, failed = [], []

    for feature_id in feature_to_files:
        skill_path = skills_dir / feature_id / "SKILL.md"
        if not skill_path.exists():
            print(f"[update-emit] {feature_id}: SKILL.md not found, skipping",
                  file=sys.stderr)
            failed.append({"feature": feature_id, "reason": "skill not found"})
            continue
        existing = skill_path.read_text(encoding="utf-8")
        domain = _domain_from_skill(existing, feature_id)
        source_blob = _collect_source_blob(domain, repo_root, index_dict)
        if not source_blob.strip():
            print(f"[update-emit] {feature_id}: no source found, skipping",
                  file=sys.stderr)
            failed.append({"feature": feature_id, "reason": "no source"})
            continue

        prompt = (
            PHASE_2_UPDATE_PROMPT_PREFIX
            .replace("{TODAY}", date.today().isoformat())
            .replace("{EXISTING_SKILL_MD}", existing)
            .replace("{SOURCE_BLOB}", source_blob)
        )
        prompt = prompt + "\n\n--- STAGE 3 GENERATE TEMPLATE FOLLOWS ---\n\n" + (
            STAGE_3_GENERATE_PROMPT
            .replace("{DOMAIN_ID}", feature_id)
            .replace("{DOMAIN_NAME}", feature_id)
            .replace("{DOMAIN_DESCRIPTION}", "")
            .replace("{TODAY}", date.today().isoformat())
            .replace("{SOURCE_BLOB}", "(see above)")
        )
        target = prompts_dir / f"{feature_id}.md"
        target.write_text(prompt, encoding="utf-8")
        written.append(str(target))
        print(f"[update-emit] {feature_id}: wrote {target} ({len(prompt)} chars)",
              file=sys.stderr)

    return {"written": written, "skipped": [], "failed": failed}


def _bump_version(existing_md: str) -> tuple:
    m = re.search(r"^version:\s*(\d+)", existing_md, re.MULTILINE)
    existing_version = int(m.group(1)) if m else 1
    return existing_version, existing_version + 1


def ingest_responses(repo_root: str | Path, *,
                     responses_dir: str | Path | None = None,
                     commit: bool = False,
                     feature: str | None = None,
                     validate_schema: bool = True) -> dict:
    """Read each per-feature response, bump version + last_updated, validate
    against the artifact-3 contract, write the refreshed SKILL.md, and
    optionally commit. With validate_schema=False, the validation gate is
    skipped (not recommended — corrupted SKILL.mds will be written)."""
    repo_root = Path(repo_root).resolve()
    skills_dir = _resolve_skills_dir(repo_root)
    if skills_dir is None:
        return {"updated": [], "failed": [], "reason": "no skills directory"}
    responses_dir = Path(responses_dir or (repo_root / ".skill-gen" / ".update-responses"))

    if feature:
        response_files = [responses_dir / f"{feature}.md"]
    else:
        response_files = sorted(responses_dir.glob("*.md"))

    today = date.today().isoformat()
    updated, failed = [], []
    for rp in response_files:
        feature_id = rp.stem
        if not rp.exists():
            failed.append({"feature": feature_id, "reason": "response missing"})
            continue
        skill_path = skills_dir / feature_id / "SKILL.md"
        if not skill_path.exists():
            failed.append({"feature": feature_id, "reason": "skill not found"})
            continue
        existing = skill_path.read_text(encoding="utf-8")
        old_ver, new_ver = _bump_version(existing)
        content = _strip_markdown_fence(rp.read_text(encoding="utf-8"))
        if not content.strip():
            failed.append({"feature": feature_id, "reason": "empty response"})
            continue
        # Force the version bump in case the AI didn't honor the +1 instruction
        content = re.sub(
            r"^version:\s*\d+",
            f"version: {new_ver}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        # Force today's date in case the AI returned a stale or missing one
        content = re.sub(
            r"^last_updated:\s*.*$",
            f"last_updated: {today}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if validate_schema:
            vres = validate(content, path=str(rp))
            for w in vres.warnings:
                print(f"[update-ingest] {feature_id}: WARN: {w}", file=sys.stderr)
            if not vres.ok:
                print(f"[update-ingest] {feature_id}: validation FAILED, NOT writing — "
                      f"fix {rp} and re-run:", file=sys.stderr)
                for e in vres.errors:
                    print(f"  ERROR: {e}", file=sys.stderr)
                failed.append({"feature": feature_id, "reason": "validation failed",
                               "errors": vres.errors})
                continue
        skill_path.write_text(content, encoding="utf-8")
        updated.append(str(skill_path))
        print(f"[update-ingest] {feature_id}: v{old_ver} -> v{new_ver}",
              file=sys.stderr)

    if commit and updated:
        try:
            subprocess.run(
                ["git", "-C", str(repo_root), "add", *updated],
                check=True, capture_output=True,
            )
            features = ", ".join(sorted(set(Path(p).parent.name for p in updated)))
            subprocess.run(
                ["git", "-C", str(repo_root), "commit",
                 "-m", f"chore: update {features} skill(s) (auto)"],
                check=True, capture_output=True,
            )
            print(f"[update-ingest] committed {len(updated)} skill update(s)",
                  file=sys.stderr)
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode() if e.stderr else str(e)
            print(f"[update-ingest] git commit failed: {err}", file=sys.stderr)

    return {"updated": updated, "failed": failed}
