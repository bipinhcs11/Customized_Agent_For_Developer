---
name: skill-updater
description: Refresh one or more existing `SKILL.md` files after the underlying Java source has changed, using the Phase 2 incremental updater (`update-emit` / `update-ingest`). Use when the developer says "update skills", "refresh the skill for <feature>", "this skill is out of date", "the SKILL.md doesn't match the code anymore", or after merging a PR that touched a documented feature. Drives a one- or two-turn emit/ingest cycle per affected feature — no API keys, no outbound network calls, and no need to re-run the full Crawl → Plan → Generate → Link pipeline.
---

# Skill Updater

This skill keeps already-generated `SKILL.md` files in sync with the code after the initial run of the [skill-generator](../skill-generator/SKILL.md) skill. It runs the Phase 2 incremental updater: `update-emit` maps recent changes to existing feature skills and writes one refresh prompt per affected feature; you (the host agent) regenerate the SKILL.md body; `update-ingest` bumps `version`, sets `last_updated`, validates, and writes the result.

## When to use this skill

Invoke when the developer says any of:

- "Update the skills" / "refresh the skills" (after a merge or a batch of commits)
- "The `<feature>` skill is out of date" / "doesn't match the code anymore"
- "Refresh the skill for `<feature-id>`"
- Immediately after a code review or PR merge that touched a feature with an existing `.github/skills/<feature-id>/SKILL.md`

Do **not** invoke for:

- A repo with no `.github/skills/` or `skills/` directory yet — that needs the [skill-generator](../skill-generator/SKILL.md) skill's full pipeline (Crawl → Plan → Generate → Link) first.
- A change that introduces a **brand-new feature** (new top-level package, new Struts action, new Quartz job) with no existing skill folder. `update-emit` will report these files as unclaimed — see "New features" below.
- Hand-editing a `SKILL.md` directly. Always go through `update-ingest` so `version` and `last_updated` stay consistent.

## Pre-flight

Confirm with the developer:

| Item | How to ask |
|---|---|
| Target repo path | "Which repo's skills should I refresh? Give me the absolute path." |
| Skills already exist | Check for `<target>/.github/skills/*/SKILL.md` (generated repos) or `<target>/skills/*/SKILL.md` (this repo's reference skills). If neither exists, redirect to skill-generator instead. |
| What changed | "Should I look at `git diff` for you, or is there a specific feature you want refreshed regardless of git state?" |
| Where this skill-generator repo is checked out | Needed for `python3 -m tools.skill_generator.cli`. |

Set shell variables and `cd` into this repo so the module path resolves:

```bash
AGENT=/path/to/FeatureBased_Skill_Generator_Agent   # this repo
TARGET=/path/to/the/java/repo                       # the repo whose skills to refresh
cd "$AGENT"
```

## Step 1 — Identify affected features (`update-emit`)

Default: let the diff drive it. `update-emit` runs `git diff --name-only` between `--base` (default `HEAD~1`) and `--head` (default `HEAD`), maps each changed file to an existing feature by matching its basename against filenames mentioned in that feature's `SKILL.md`, then re-crawls the repo and writes one prompt per affected feature.

```bash
python3 -m tools.skill_generator.cli update-emit --repo "$TARGET"
```

To refresh a specific feature regardless of git state (e.g., the developer just asked "refresh file-delivery"), skip the diff entirely:

```bash
python3 -m tools.skill_generator.cli update-emit --repo "$TARGET" --feature file-delivery
```

To compare a wider range (e.g., everything merged since a release tag):

```bash
python3 -m tools.skill_generator.cli update-emit --repo "$TARGET" --base v1.2.0 --head HEAD
```

Each prompt lands at `$TARGET/.skill-gen/.update-prompts/<feature-id>.md`. Report to the developer:

- Which feature ids were affected
- Any changed files that **no existing skill claims** — `update-emit` prints `[update] <file>: no existing skill claims this file — may be a new feature; full re-plan needed` for these to stderr. Collect that list; see "New features" below.

If no features were affected, say so and stop — there is nothing to refresh.

## Step 2 — Respond (one host-agent turn per affected feature)

Each prompt contains the existing `SKILL.md` in full, followed by the **new** source for every class/XML/SQL/shell file the prior skill referenced, followed by the same Stage 3 generate-template contract used for first-time generation.

For each `$TARGET/.skill-gen/.update-prompts/<feature-id>.md`:

1. Read the existing SKILL.md and the new source side by side.
2. Re-generate the **full** SKILL.md body so it accurately reflects the new source — same artifact-3 contract as Stage 3 (required frontmatter fields, body sections in order, citations to `ClassName.methodName()`, `none found` for empty sections, no Java code blocks).
3. Increment `version` by 1 and set `last_updated` to today's date — `update-ingest` will force-correct these anyway if you miss it, but get them right.
4. Preserve `related_skills` from the existing skill unless the change obviously adds, removes, or alters a cross-domain relationship — if it does, update that section and note it to the developer (full re-link via `link-emit`/`link-ingest` is the alternative for large relationship changes).
5. Write your response to `$TARGET/.skill-gen/.update-responses/<feature-id>.md`.

Use the same reference skills as quality bar: `skills/file-delivery/SKILL.md`, `skills/invoice-compare/SKILL.md`, `skills/payment-method-determination/SKILL.md`.

## Step 3 — Apply updates (`update-ingest`)

```bash
python3 -m tools.skill_generator.cli update-ingest --repo "$TARGET"
```

This validates each response against the artifact-3 contract, force-corrects `version` (existing + 1) and `last_updated` (today) even if the response got them wrong, and writes the refreshed `SKILL.md`. A response that fails validation is **not** written — the exit code is 2 and each `FAILED: …` line names the feature and the validation errors. Report these to the developer and offer to regenerate just that feature's response.

Add `--commit` once the developer is happy with the diff, to commit the refreshed skills automatically:

```bash
python3 -m tools.skill_generator.cli update-ingest --repo "$TARGET" --commit
```

This commits with the message `chore: update <feature1>, <feature2> skill(s) (auto)`. Without `--commit`, the developer reviews and commits manually.

To apply only one feature's response (e.g., after fixing a single `FAILED` one):

```bash
python3 -m tools.skill_generator.cli update-ingest --repo "$TARGET" --feature file-delivery
```

## New features (files no skill claims)

If `update-emit` reported changed files that no existing skill mentions, that is a signal a **new business feature** was added (new package, new Struts action, new Quartz job, etc.). The incremental updater intentionally does not handle this — it only refreshes skills that already exist. Tell the developer:

> These files don't belong to any documented feature yet: `<list>`. The incremental updater can't create a new skill — re-run the [skill-generator](../skill-generator/SKILL.md) pipeline (at least Stage 2 Plan, to detect the new domain, through Stage 4 Link) so the new feature gets its own `SKILL.md` and is cross-linked with the existing ones.

## Hard rules

- **Never** hand-edit a `SKILL.md`. Always go through `update-ingest` so `version` and `last_updated` stay consistent and the artifact-3 contract is re-validated.
- **Never** skip `update-ingest`'s validation gate with `--no-validate` unless the developer explicitly asks — a corrupted `SKILL.md` is worse than a stale one.
- **Never** add HTTP/API client code, third-party Python deps, or outbound calls to LLM endpoints — the same stdlib-only, host-agent-driven constraint as skill-generator applies here.
- **Never** invent a new feature's skill via this updater — redirect to skill-generator for new domains.
- Preserve the existing `related_skills` frontmatter and Related Skills table unless the source change clearly affects a cross-domain dependency.

## Common failures and what to do

| Symptom | Cause | Action |
|---|---|---|
| `update-emit` reports "no features affected by these changes" | The diff range doesn't touch any file an existing skill mentions | Confirm the `--base`/`--head` range with the developer, or use `--feature <id>` to force a refresh regardless of diff |
| `update-emit` reports "no skills/ or .github/skills/ found" | Target repo has never been through skill-generator | Redirect to the skill-generator skill for the first full run |
| `update-emit` reports "no source found, skipping" for a feature | The classes/files the old skill referenced no longer exist (renamed/removed) | Treat as a bigger change — re-run skill-generator's Plan stage for that area instead of a Phase 2 refresh |
| `update-ingest` reports `FAILED: <feature>` | Response missing a required frontmatter field or body section, or still contains placeholder text | Re-read the prompt's contract, regenerate the response, re-run `update-ingest --feature <feature-id>` |
| `update-ingest --commit` doesn't commit | No responses were successfully ingested (all failed validation) | Fix the failures first; `--commit` only runs when at least one skill was updated |

## Reference

- Phase 2 spec: `AGENT.md` (section "Phase 2 — The updater")
- Project-level Claude guidance: `CLAUDE.md`
- Prompt templates (single source of truth): `tools/skill_generator/prompts.py` (`PHASE_2_UPDATE_PROMPT_PREFIX`)
- Updater implementation: `tools/skill_generator/update.py`
- Full first-run pipeline: `skills/skill-generator/SKILL.md`
- Reference SKILL.mds (quality bar): `skills/file-delivery/SKILL.md`, `skills/invoice-compare/SKILL.md`, `skills/payment-method-determination/SKILL.md`
