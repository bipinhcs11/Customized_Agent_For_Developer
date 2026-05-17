# Release readiness checklist

Objective gate before this agent is recommended for **unsupervised enterprise-wide rollout** (i.e., turned on across dozens of repos with minimal hand-holding). The agent is already useful as an **internal beta** — engineers comfortable inspecting prompts/responses can run it on their own repos today.

This checklist is the contract between "works for the team that built it" and "trustworthy when an unfamiliar engineer runs it on Friday afternoon".

Legend: ✅ done · ⏳ in progress / planned · ❌ not started · ⚠️ partial

---

## 1. Pipeline correctness — write paths must be trustworthy

| | Item | Notes |
|---|---|---|
| ✅ | **SKILL.md schema validation gates every ingest** | `tools/skill_generator/validate.py`; wired into `generate-ingest`, `update-ingest`, `link-ingest`. Refuses to write on contract violation. PR #5. |
| ✅ | **Link stage updates both sides of every relationship** | Reverse direction uses inverted types (`called-by`/`extended-by`/`configured-by`); `shares` stays symmetric. PR #5; `AGENT.md:97`. |
| ✅ | **`update-ingest` forces `last_updated` to today** | Was only forcing `version`. PR #5. |
| ✅ | **Per-bullet citation enforcement** | `_check_per_bullet_citations` walks every bullet/numbered-list line in citation-required sections and warns on specific uncited bullets (with preview text). Table rows and template hints skipped. Warning-level so reference skills keep passing while real gaps are surfaced. |
| ✅ | **Untagged Java fence detection** | `_check_no_java_blocks` now scans every fenced block, not just ` ```java `. Untagged blocks whose content contains Java keywords (`public class`, `import java.`, `package com.x;`) are flagged as errors. Data Flow ASCII diagrams (no such keywords) still pass. |
| ✅ | **Placeholder text (`N/A`, `TBD`) satisfying "none found"** | `_check_no_placeholder_content` rejects sections whose content is only `N/A` / `TBD` / `TODO` / `PLACEHOLDER` / `XXX` / `---` (case-insensitive). Sentences containing those tokens as words still pass. |
| ⚠️ | **Frontmatter value type checks beyond `version`** | Empty values are rejected, but no enum validation for `project_type`/`framework`/`java_version`/etc. Soft target — the prompt contract is permissive. |
| ✅ | **Stage 3 prompts include config key-VALUES (not just key prefixes)** | `generate.py:_collect_config_pairs` reads config files at generate-time using the planner's `configKeys` and the crawler's `config_signals`, extracting matching `key=value` (properties) or dotted-path `key: value` (YAML) pairs. Config blob is appended to the source blob each domain receives. |
| ❌ | **Stage 3 source collection is domain-safe when class names repeat** | Current source lookup collapses planned classes to simple names, so `com.foo.account.User` can also pull `com.foo.auth.User`. PiggyMetrics sandbox reproduced this with `Account`, `User`, `ResourceServerConfig`, and other duplicated names across microservices. |
| ❌ | **`--skip-tests` excludes test resources, not just test Java classes** | Current crawl skips Java files flagged as tests but still indexes `src/test/resources/*.yml`, which can leak test-only config into Stage 3 prompts. |
| ❌ | **`update-ingest` inserts `last_updated` when AI omitted the field** | With `--no-validate`, a missing field slips through. Strict mode catches it via the missing-required-field rule. |
| ❌ | **`link-ingest` returns non-zero exit on partial-success runs** | If `from` writes and `to` fails validation, half-applied state with green CLI. |
| ❌ | **God-class split contradiction resolved** | Codex Medium #5: `plan.py` strips `method_names`, `prompts.py` advertises `ClassName.methodGroup*`, `generate.py` can't resolve the method-group form. Needs design decision (restore signal or drop syntax). |
| ❌ | **`update.py` basename-only file→feature mapping handles ambiguity** | Files with the same basename across domains all get updated. No ambiguity warning. |
| ❌ | **`_domain_from_skill` regex doesn't lose unmentioned classes** | If the original SKILL.md omitted a class, the updater can never re-discover it. Compounds first-run errors. |

## 2. Output quality — what Copilot/Claude actually consume

| | Item | Notes |
|---|---|---|
| ✅ | **All three hand-authored reference SKILL.mds validate clean** | `file-delivery`, `invoice-compare`, `payment-method-determination`. Regression-tested in `tests/test_validate.py`. |
| ✅ | **One verified end-to-end run on a real microservices repo** | FTGO (358 classes, 12 services, 9 domains identified). `verification-output/VERIFICATION_REPORT.md`. Under v0.2 API mode; prompts unchanged. |
| ❌ | **Config values survive Stage 3 truncation** | Config blobs are appended after Java source, then `_build_prompt` truncates the combined blob at 24KB. In the PiggyMetrics sandbox, the account/statistics/notification prompts were truncated before any `--- CONFIG:` section appeared. |
| ❌ | **Chunk-and-merge for domains > 24KB of source** | Stage 3 currently truncates with a marker. Acceptable for beta; not for enterprise — large domains are exactly where premium-request savings would be highest. |
| ❌ | **Link prompt sees enough of each SKILL.md** | Currently 600 chars per skill (`link.py:36`) — roughly frontmatter + Purpose. Can't identify cross-references buried in Key Classes / Data Flow / External Dependencies. |
| ❌ | **Re-verified end-to-end under v0.3 host-agent mode** | The FTGO run was v0.2; output is identical-in-principle but a fresh capture under current code would close the trust gap. |

## 3. Testing & verification

| | Item | Notes |
|---|---|---|
| ✅ | **Unit tests cover validator, crawler, generate helpers** | 172 tests; runs in <13s. `python3 -m unittest discover -v`. |
| ❌ | **Integration test on a tiny fixture repo end-to-end** | No test exercises `crawl → plan → generate → link → validate` as one pipeline. Codex's "Needs Improvement". |
| ❌ | **Plan-stage parsing has a contract test** | `plan.py:_parse_plan_json` accepts whatever JSON the AI returns; no required-field check at parse time. |
| ❌ | **CI runs the full suite on each PR** | No workflow file under `.github/workflows/` for the agent repo itself. |

## 4. Documentation honesty

| | Item | Notes |
|---|---|---|
| ✅ | **README license section reflects actual `LICENSE`** | Was "no license yet"; now "MIT — see LICENSE". |
| ✅ | **`tools/skill_generator/README.md` tool version matches code** | Was `0.3.0`/`schema 1`; now `0.2.0`/`schema 2` to match `crawler.py`. |
| ✅ | **README has a visible "internal beta" status badge + line** | Sets expectations before someone tries this on a 200-feature monolith. |
| ✅ | **Enterprise agent/model selection guidance exists** | `docs/enterprise-agent-selection-guide.md` explains when to use stronger reasoning sessions, normal team defaults, Copilot/Claude/Codex consumption, and VS Code/IntelliJ rollout. |
| ✅ | **AGENT.md documents the reverse-direction link types** | Was a silent code behavior; now in the spec. |
| ✅ | **`CLAUDE.md` no longer says `tools/skill_generator/` is "to be built"** | Stale doc; the package clearly exists. |
| ⏳ | **Bump `TOOL_VERSION` to `0.3.0` to reflect the host-agent milestone** | Constant in `crawler.py` still says `0.2.0`; docs flag the intent. |
| ⏳ | **`verification-output/VERIFICATION_REPORT.md` re-run under v0.3** | Existing report has a clear "historical" preamble; a fresh run would replace it. |

## 5. Operability — packaging and multi-repo

| | Item | Notes |
|---|---|---|
| ⏳ | **Packaging: `setup.py`/`pyproject.toml` so `pipx install skill-gen` works** | Today the docs use `python3 -m tools.skill_generator.cli`. Either ship as a package or make the docs consistent. |
| ❌ | **Doctor estimates multi-module microservice domains correctly** | The current heuristic counts distinct top-two package levels, so a repo like PiggyMetrics collapses all `com.piggymetrics.*` services into one likely feature even though the module layout clearly indicates account/auth/statistics/notification/platform domains. |
| ❌ | **Multi-repo orchestration config** | `agent-config.yml` is in the roadmap; no implementation yet. Blocks "50+ enterprise repos in one pass". |
| ❌ | **Central team runbook for approved model/session tiers** | The repo now has guidance, but each enterprise still needs its own policy for which Claude/Codex/Copilot tiers are approved for first-run generation, routine updates, and daily consumption. |
| ❌ | **CI hook variant for the updater** | `update-emit` / `update-ingest` work manually; no GitHub Action template for PR-merge-triggered updates. |
| ❌ | **A dry-run / preview mode for `skill-gen validate` in CI** | Useful for PR checks on target repos. |

---

## Verdict by audience

- **Hands-on adopters (the engineers who wrote this):** ✅ ready today.
- **Other engineers in the same org, with light hand-holding:** ✅ ready once the remaining correctness rows are addressed (domain-safe source collection, `--skip-tests` resource handling, config truncation, partial link-write exit status, god-class decision, basename ambiguity, and updater class rediscovery).
- **Unsupervised enterprise-wide rollout across many teams:** ❌ not yet. Sections 1, 2, and 3's ❌ rows are all blockers, not nice-to-haves. Sections 4 and 5 are mostly polish.

This file should be updated as items move state. PRs that complete a row should reference this file in their description.
