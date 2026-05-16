"""
Phase 2 — Incremental updater.

Reads `git diff` for changed Java/XML/SQL/shell files, maps each changed file
to a feature id by looking at the existing skill folders, then re-runs Stage 3
only for affected features. Bumps `version` and `last_updated`. Commits with
an auto-generated message.

Trigger surfaces:
  - GitHub Action on PR merge (preferred): run via CLI
  - Git pre-commit hook: same CLI
  - File watcher: same CLI
  - Manual: `skill-gen update --feature file-delivery`
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from .claude_client import ClaudeClient
from .crawler import crawl
from .prompts import PHASE_2_UPDATE_PROMPT_PREFIX, STAGE_3_GENERATE_PROMPT
from .generate import _collect_source_blob, _strip_markdown_fence


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
    # Fallback: anything currently staged or unstaged
    out = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True, text=True, check=False,
    )
    return [l[3:].strip() for l in out.stdout.splitlines() if l.strip()]


def _map_files_to_features(changed_files: list, skills_dir: Path) -> dict:
    """For each existing SKILL.md, read its Key Classes & Files table to learn
    which file paths belong to that feature. Return {feature_id: [changed_files]}.

    This is a simple substring match against file basenames mentioned in the
    skill. Not perfect, but good enough for Phase 2 v0 — if a file isn't claimed
    by any skill, it's logged and ignored (likely a new feature, which requires
    a full re-plan)."""
    feature_files: dict = {}
    if not skills_dir.exists():
        return feature_files

    skill_to_basenames: dict = {}
    for skill_path in skills_dir.glob("*/SKILL.md"):
        feature_id = skill_path.parent.name
        text = skill_path.read_text(encoding="utf-8")
        # Pull all .java / .xml / .sql / .sh / .yml / .properties basenames out of the body
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


def _bump_version_and_date(existing_md: str) -> tuple:
    """Return (existing_version_int, new_md_template_substring) so the generator
    knows what version to land on."""
    m = re.search(r"^version:\s*(\d+)", existing_md, re.MULTILINE)
    existing_version = int(m.group(1)) if m else 1
    return existing_version, existing_version + 1


def run(repo_root: str | Path, *, base: str = "HEAD~1", head: str = "HEAD",
        feature: str | None = None, dry_run: bool = False,
        model: str | None = None, commit: bool = False) -> dict:
    repo_root = Path(repo_root).resolve()
    skills_dir = repo_root / ".github" / "skills"
    if not skills_dir.exists():
        # Fall back to in-repo `skills/` for repos using that layout
        skills_dir = repo_root / "skills"
    if not skills_dir.exists():
        print(f"[update] no skills/ or .github/skills/ found in {repo_root}", file=sys.stderr)
        return {"updated": [], "skipped": [], "reason": "no skills directory"}

    if feature:
        feature_to_files = {feature: ["(manual trigger)"]}
    else:
        changed = _git_changed_files(repo_root, base, head)
        print(f"[update] {len(changed)} files changed between {base}..{head}",
              file=sys.stderr)
        feature_to_files = _map_files_to_features(changed, skills_dir)

    if not feature_to_files:
        print("[update] no features affected by these changes", file=sys.stderr)
        return {"updated": [], "skipped": [], "reason": "no affected features"}

    # Re-crawl the repo so we have a fresh index for the generator
    print(f"[update] re-crawling {repo_root}...", file=sys.stderr)
    index = crawl(repo_root)
    from dataclasses import asdict
    index_dict = asdict(index)

    client_kwargs = {"dry_run": dry_run}
    if model:
        client_kwargs["model"] = model
    client = ClaudeClient(**client_kwargs)

    updated: list = []
    failed: list = []

    for feature_id, files in feature_to_files.items():
        skill_path = skills_dir / feature_id / "SKILL.md"
        if not skill_path.exists():
            print(f"[update] {feature_id}: SKILL.md not found, skipping", file=sys.stderr)
            failed.append({"feature": feature_id, "reason": "skill not found"})
            continue

        existing = skill_path.read_text(encoding="utf-8")
        old_ver, new_ver = _bump_version_and_date(existing)

        # Reconstruct a minimal domain dict by reading classes the skill claims
        domain = _domain_from_skill(existing, feature_id)
        source_blob = _collect_source_blob(domain, repo_root, index_dict)
        if not source_blob.strip():
            print(f"[update] {feature_id}: no source found, skipping", file=sys.stderr)
            failed.append({"feature": feature_id, "reason": "no source"})
            continue

        prompt = (
            PHASE_2_UPDATE_PROMPT_PREFIX
            .replace("{TODAY}", date.today().isoformat())
            .replace("{EXISTING_SKILL_MD}", existing)
            .replace("{SOURCE_BLOB}", source_blob)
        )
        # Append the Stage-3 generator template so the AI has the structural rules
        prompt = prompt + "\n\n--- STAGE 3 GENERATE TEMPLATE FOLLOWS ---\n\n" + (
            STAGE_3_GENERATE_PROMPT
            .replace("{DOMAIN_ID}", feature_id)
            .replace("{DOMAIN_NAME}", feature_id)
            .replace("{DOMAIN_DESCRIPTION}", "")
            .replace("{TODAY}", date.today().isoformat())
            .replace("{SOURCE_BLOB}", "(see above)")
        )

        print(f"[update] {feature_id}: regenerating from {len(source_blob)} chars of source...",
              file=sys.stderr)
        try:
            content = client.complete(prompt, max_tokens=4096)
        except Exception as e:
            print(f"[update] {feature_id}: FAILED — {e}", file=sys.stderr)
            failed.append({"feature": feature_id, "reason": str(e)})
            continue

        content = _strip_markdown_fence(content)
        # Force the version bump in case the AI didn't honor the +1 instruction
        content = re.sub(
            r"^version:\s*\d+",
            f"version: {new_ver}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        skill_path.write_text(content, encoding="utf-8")
        updated.append(str(skill_path))
        print(f"[update] {feature_id}: v{old_ver} → v{new_ver}", file=sys.stderr)

    if commit and updated and not dry_run:
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
            print(f"[update] committed {len(updated)} skill update(s)", file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(f"[update] git commit failed: {e.stderr.decode() if e.stderr else e}",
                  file=sys.stderr)

    return {"updated": updated, "failed": failed}


def _domain_from_skill(skill_md: str, feature_id: str) -> dict:
    """Reconstruct the minimal domain dict the generator needs from an existing
    SKILL.md. Pulls class names + file references out of the Key Classes & Files
    section and the data flow."""
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
