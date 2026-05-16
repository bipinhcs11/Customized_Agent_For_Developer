# CLAUDE.md — FeatureBased Skill Generator Agent

This file configures Claude's behaviour when working in this project folder (via Cowork or Claude Code).

---

## What this repo is

A customizable AI agent that reads any Java repository — Spring Boot, Spring MVC, Struts, Quarkus, Spring Batch, Quartz, raw servlets, or any mixed/legacy combination — identifies its business features automatically, and writes one rich `SKILL.md` file per feature. Those skill files serve as persistent, AI-readable context for GitHub Copilot and Claude, so neither has to re-discover the domain from scratch on every premium request.

The repo also contains the Phase-2 updater that keeps generated skills current as code evolves.

**Read `AGENT.md` first** for the full pipeline specification before doing any work in this repo. Read `OPUS_PROMPT.md` for the original problem statement and rationale.

---

## What Claude should always do

- **Read `AGENT.md` first** — it defines the four-stage pipeline (Crawl → Plan → Generate → Link), the Phase-2 updater triggers, the SKILL.md standard, and the supported Java flavors.
- **Read the artifact-3 SKILL.md standard** before generating or editing any SKILL.md: https://claude.ai/public/artifacts/1689b220-c09f-467c-a8af-1eb3bb1a30fe
- **Read the relevant reference skill** when doing feature-specific work: `skills/<feature>/SKILL.md`.
- **Treat the three reference skills as the quality bar** — generated skills must match their format and depth exactly.
- **Cite `ClassName.methodName()`** for every rule, entry point, and edge case in a SKILL.md.
- **Write the literal string "none found"** in any section that has no content — never omit a section.
- **Frame work in terms of premium-request savings and accuracy** — the whole product exists to make Copilot answer the right thing first time, on a 300-request/month enterprise budget.

---

## Available and planned skills

| Skill | Path | Status | Triggers |
|---|---|---|---|
| File Delivery (reference) | `skills/file-delivery/SKILL.md` | Present | "file delivery", "FileDelivery" |
| Invoice Compare (reference) | `skills/invoice-compare/SKILL.md` | Present | "invoice compare", "InvoiceCompare" |
| Payment Method Determination (reference) | `skills/payment-method-determination/SKILL.md` | Present | "payment method", "PaymentMethodDetermination" |
| Skill Generator | `skills/skill-generator/SKILL.md` | To be built | "generate skills for this repo", "scan Java repo", "create SKILL.md files" |
| Skill Updater | `skills/skill-updater/SKILL.md` | To be built | "update skills", "refresh skill", "skill out of date" |

---

## Output locations

| File type | Where it lives |
|---|---|
| Reference SKILL.mds in THIS repo | `skills/<feature>/SKILL.md` |
| Generated SKILL.mds in a TARGET repo | `.github/skills/<feature>/SKILL.md` |
| Reference Java examples | `examples/<feature>/` (read-only — illustrative style only) |
| Python CLI source | `tools/skill_generator/` (to be built) |
| Multi-repo orchestration config | `agent-config.yml` (to be built) |
| Original problem statement | `OPUS_PROMPT.md` (read-only reference) |

---

## Java flavor handling

The agent must handle any of these flavors and produce SKILL.mds that accurately describe the actual code:

- Spring Boot 2.x / 3.x — annotation-driven REST + Data JPA
- Spring MVC — XML or annotation configuration
- Struts 1 / 2 — XML action mappings
- Quarkus — JAX-RS annotations
- Spring Batch — Job / Step / Processor
- Quartz Scheduler — cron-driven jobs
- Raw servlets — web.xml URL patterns
- Mixed legacy — multiple of the above in one repo

**Important:** the Spring Boot 3.x conventions in `examples/` and the template files are the *quality bar* for the three reference features in this repo, **not** instructions to impose on target repos. When scanning a Struts codebase, the generated SKILL.md describes Struts, not Spring Boot.

---

## What Claude should NOT do

- Do not generate Java code as a primary product — the agent emits `SKILL.md` files. The Java in `examples/` is illustrative.
- Do not invent a SKILL.md format — use the artifact-3 standard verbatim.
- Do not embed Java code blocks in a SKILL.md body — use tables and cited rules instead.
- Do not edit a generated SKILL.md by hand — re-run the updater so version/last_updated stay consistent.
- Do not skip or omit a SKILL.md section — empty sections contain the literal `none found`.
- Do not assume a target repo is Spring Boot — the Plan stage decides based on actual signals (XML wiring, annotations, package layout).
- Do not generate test classes, Spring Security configuration, or Lombok in the reference examples unless asked.
- Do not use bullet/list formatting in conversational responses unless the user asks for it.

---

## Style references (for reference examples only)

These apply only to the three reference Java implementations under `examples/`. Generated SKILL.mds describe whatever the target repo actually uses.

| Concern | Reference style |
|---|---|
| Framework | Spring Boot 3.x, Java 17+ |
| ORM | Spring Data JPA (JDBC Template for complex queries) |
| Database | PostgreSQL (MySQL dialect supported) |
| Logging | SLF4J + Logback |
| Validation | Jakarta Bean Validation |
| Build | Maven |
| Injection | Constructor only (no field `@Autowired`) |
| Delete | Soft delete (`is_active = false`); never hard DELETE |
| Enums | Stored as VARCHAR (never ordinal) |
| Audit columns | Every table has `created_at`, `updated_at`, `created_by`, `is_active` |

---

## Background

The original problem statement is in `OPUS_PROMPT.md`. The three Claude artifacts that informed the design are referenced there:

- Artifact 2 (the four-stage pipeline spec): https://claude.ai/public/artifacts/3467e791-5cf1-44bc-be5d-05119a2018c8
- Artifact 3 (the SKILL.md standard): https://claude.ai/public/artifacts/1689b220-c09f-467c-a8af-1eb3bb1a30fe
- Artifact 1 (v2 analyzer design): https://claude.ai/public/artifacts/89b22944-5134-4295-8836-938432f48b06
