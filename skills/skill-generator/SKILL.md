---
name: skill-generator
description: Analyze a Java repository (Spring Boot, Spring MVC, Struts, Quarkus, Spring Batch, Quartz, raw servlets, or mixed/legacy) and generate one `SKILL.md` per business feature into `.github/skills/<feature-id>/`, so GitHub Copilot and Claude have persistent feature context. Use when the developer says "analyze this project/repo/module", "scan this Java repo", "generate skills for this repo", "create SKILL.md files", "document this codebase for Copilot", or asks to run the FeatureBased Skill Generator pipeline. Drives a four-stage emit/ingest workflow (Crawl → Plan → Generate → Link) using the local Python CLI; every LLM turn happens inside this AI session — no API keys, no outbound network calls.
---

# Skill Generator

This skill walks the host AI session (Claude Code, GitHub Copilot Chat, Codex, Claude Cowork) through the four-stage FeatureBased Skill Generator pipeline. The Python CLI in `tools/skill_generator/` is deterministic and stdlib-only — it never calls an LLM directly. Each LLM-dependent stage emits a prompt file; you (the host agent) read it, produce the response, save it back to disk, and the CLI ingests it.

The final output is one `SKILL.md` per business feature under `<target-repo>/.github/skills/<feature-id>/`, each conforming to the [artifact-3 SKILL.md standard](https://claude.ai/public/artifacts/1689b220-c09f-467c-a8af-1eb3bb1a30fe).

## When to use this skill

Invoke when the developer asks any of:

- "Analyze this project / repo / module"
- "Generate skills for this repo"
- "Scan this Java repo and create SKILL.md files"
- "Document this codebase for Copilot / Claude"
- "Run the skill generator on `<path>`"
- "Refresh the skills for this feature" (→ jump to Phase 2)

Do **not** invoke for: writing new Java code, editing an existing SKILL.md by hand (re-run the updater instead), or anything in a repo that is not Java.

## Pre-flight

Before starting, confirm with the developer:

| Item | How to ask |
|---|---|
| Target repo path | "Which Java repo should I analyze? Give me the absolute path." |
| Python 3.10+ available | `python3 --version` — abort with a clear message if older |
| Where this skill-generator repo is checked out | Needed for `python3 -m tools.skill_generator.cli`. If unknown, default to `~/Documents/Customized_Agent_For_Developers/FeatureBased_Skill_Generator_Agent` |
| Skip tests? | Off by default. Pass `--skip-tests` to the crawler if the developer says yes |

Set two shell variables for the session and use them everywhere:

```bash
AGENT=/path/to/FeatureBased_Skill_Generator_Agent   # this repo
TARGET=/path/to/the/java/repo                       # the repo to analyze
```

Then `cd "$AGENT"` so `python3 -m tools.skill_generator.cli` resolves.

## Stage 1 — Crawl (no LLM turn)

Walks the target repo, writes an index of every Java class, XML signal, config key, SQL file, and shell script.

```bash
python3 -m tools.skill_generator.cli crawl "$TARGET" \
    --output "$TARGET/.skill-gen/.index.json"
```

Report the printed stats line (`X java, Y xml, Z config, …`) to the developer. If `java_classes == 0`, stop and report — the repo has no Java sources the crawler recognises.

## Stage 2 — Plan (one host-agent turn)

### Emit

```bash
python3 -m tools.skill_generator.cli plan-emit "$TARGET/.skill-gen/.index.json"
```

### Respond (this is your turn)

1. Read `$TARGET/.skill-gen/plan-prompt.md`.
2. Follow its instructions exactly. The prompt asks for a single JSON object with `projectType`, `framework`, `buildSystem`, `javaVersion`, `warnings[]`, and `domains[]`. Reply with that JSON only — no markdown fence, no commentary.
3. Write your response to `$TARGET/.skill-gen/plan-response.md`.

### Ingest

```bash
python3 -m tools.skill_generator.cli plan-ingest \
    "$TARGET/.skill-gen/plan-response.md"
```

### Confirm with the developer

Show the developer the resulting `.plan.json` (domain ids, names, class counts, confidence). Ask them to:

- Toggle off any domains they do not want documented
- Merge or rename any domains that look wrong
- Confirm before proceeding

**Halt here until the developer confirms.** The pipeline must not move to Stage 3 until they say so. If they edit the plan by hand, re-read it before continuing.

## Stage 3 — Generate (one host-agent turn per approved domain)

### Emit

```bash
python3 -m tools.skill_generator.cli generate-emit \
    "$TARGET/.skill-gen/.plan.json" --repo "$TARGET"
```

To restrict to a subset of domains (e.g., during a first pilot run), repeat `--only <domain-id>`.

### Respond (one turn per domain)

For each file in `$TARGET/.skill-gen/.generate-prompts/<domain-id>.md`:

1. Read the prompt — it contains the domain's source files, relevant XML, config keys, and the SKILL.md template contract.
2. Produce a SKILL.md body that conforms to artifact-3:
   - Required frontmatter fields: `skill`, `domain`, `version`, `project_type`, `framework`, `java_version`, `legacy`, `status`, `flags`, `related_skills`, `generated_by`, `last_updated`.
   - Body sections in this exact order: Purpose, Entry Points, Business Logic (Core Flow + Validation Rules + Business Rules), Key Classes & Files, Data Flow, Database & Storage, External Dependencies, Error Handling, Edge Cases, Legacy Notes, Related Skills, AI Agent Instructions.
   - Cite `ClassName.methodName()` for every entry point, validation rule, business rule, and edge case.
   - Use the literal string `none found` for empty sections — never omit a section.
   - No Java code blocks in the body. Tables and cited rules only.
   - Describe the target repo's actual conventions (Struts, raw servlets, Quarkus, etc.) — do not impose Spring Boot patterns on a non-Spring-Boot repo.
3. Write your response to `$TARGET/.skill-gen/.generate-responses/<domain-id>.md`.

Use the three reference skills in this repo as the quality bar: `skills/file-delivery/SKILL.md`, `skills/invoice-compare/SKILL.md`, `skills/payment-method-determination/SKILL.md`.

### Ingest

```bash
python3 -m tools.skill_generator.cli generate-ingest \
    "$TARGET/.skill-gen/.plan.json" --repo "$TARGET"
```

Add `--force` only if the developer explicitly asks to overwrite an existing SKILL.md. Add `--only <domain-id>` to ingest a subset. The ingest exit code is 2 if any domain failed — report each `FAILED: …` line to the developer and offer to re-run just that domain after they fix the response.

## Stage 4 — Link (one host-agent turn)

### Emit

```bash
python3 -m tools.skill_generator.cli link-emit "$TARGET/.github/skills"
```

### Respond

1. Read `$TARGET/.skill-gen/link-prompt.md`. It contains the first ~600 characters of every generated SKILL.md.
2. Identify cross-domain dependencies. Signals: direct class instantiation across domains, injected services from another domain, shared DAOs, exceptions thrown in one domain caught in another, config values shared across domains.
3. Reply with a JSON object `{"links": [{"from": "...", "to": "...", "reason": "...", "type": "calls|shares|extends|configures"}, ...]}` — JSON only, no markdown fence.
4. Save to `$TARGET/.skill-gen/link-response.md`.

### Ingest

```bash
python3 -m tools.skill_generator.cli link-ingest \
    "$TARGET/.skill-gen/link-response.md" \
    --skills-dir "$TARGET/.github/skills"
```

This updates `related_skills` in each SKILL.md frontmatter and adds rows to the Related Skills table in the body.

## Finishing up

After Stage 4, tell the developer:

- Where the skills landed: `$TARGET/.github/skills/<domain-id>/SKILL.md`
- How many skills were written and how many warnings
- Suggest they `git add .github/skills && git commit -m "feat: add generated feature skills"` in the target repo
- Mention the intermediate `.skill-gen/` directory can be added to `.gitignore` or kept for re-runs

A typical 10-domain repo takes ~12 host-agent turns total (1 plan + 10 generate + 1 link).

## Phase 2 — Updater (when code changes)

After the initial generation is committed, refresh affected skills when source changes:

### Emit

```bash
python3 -m tools.skill_generator.cli update-emit --repo "$TARGET"
# Or for a single feature, skipping git diff:
python3 -m tools.skill_generator.cli update-emit --repo "$TARGET" --feature file-delivery
```

The updater maps `git diff` paths to feature ids using existing skill folders. It re-emits only the affected features — and never re-runs Stage 2 unless a brand-new feature appears (new package, new Struts action, new Quartz job).

### Respond

Same contract as Stage 3, one response per affected feature. Write each to `$TARGET/.skill-gen/.update-responses/<feature-id>.md`.

### Ingest

```bash
python3 -m tools.skill_generator.cli update-ingest --repo "$TARGET" --commit
```

`--commit` adds and commits the refreshed SKILL.mds with the message `chore: update <feature> skill (auto)`. Omit it to inspect the diff first.

## Hard rules

- **Never** add HTTP/API client code, third-party Python deps, or `urllib.request` POSTs to LLM endpoints. The `tools/skill_generator/` package is stdlib-only on purpose.
- **Never** invent a SKILL.md format. Use the artifact-3 standard verbatim.
- **Never** embed Java code blocks in a SKILL.md body. Tables and cited rules only.
- **Never** omit a SKILL.md section. Empty sections contain the literal `none found`.
- **Never** edit a generated SKILL.md by hand — re-run the updater so `version` and `last_updated` stay consistent.
- **Never** assume the target repo is Spring Boot. The Plan stage decides based on actual signals.
- **Halt for confirmation after Stage 2.** The developer reviews the plan before any source is shipped to Stage 3.

## Common failures and what to do

| Symptom | Cause | Action |
|---|---|---|
| `crawl` reports `0 java_classes` | Target path wrong, or the repo lives inside a `target/`/`build/` directory the crawler excludes | Confirm the path; if intentional, work around by copying source out of the excluded directory |
| `plan-ingest` errors on JSON parse | Response wrapped in markdown fence, or contains commentary | Re-edit the response to be JSON only; re-run `plan-ingest` |
| `generate-ingest` reports `FAILED: <domain>` | Response missing required frontmatter field or body section | Re-read the prompt's contract, regenerate the response, re-run `generate-ingest --only <domain>` |
| Stage 3 prompt truncated with overflow marker | Domain source exceeds `max_chars_per_chunk` (24,000) | Note the truncation in the SKILL.md; chunk-and-merge for very large domains is on the roadmap |
| Existing SKILL.md skipped on ingest | Idempotency guard | Add `--force` only if the developer explicitly wants to overwrite |

## Reference

- Full pipeline spec: `AGENT.md` in this repo
- Project-level Claude guidance: `CLAUDE.md`
- Original problem statement and design rationale: `OPUS_PROMPT.md`
- Prompt templates (single source of truth, used by both the Python CLI and this skill): `tools/skill_generator/prompts.py`
- Reference SKILL.mds (quality bar): `skills/file-delivery/SKILL.md`, `skills/invoice-compare/SKILL.md`, `skills/payment-method-determination/SKILL.md`
- End-to-end verification against a real microservices repo: `verification-output/VERIFICATION_REPORT.md`
