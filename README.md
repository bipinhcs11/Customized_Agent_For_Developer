# FeatureBased Skill Generator Agent

> **Turn any Java repo into AI-readable instruction files — once — so GitHub Copilot and Claude answer feature questions correctly the first time, every time, without burning your premium-request budget.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Zero outbound API calls](https://img.shields.io/badge/network-zero_outbound-green)]()
[![Verified on FTGO](https://img.shields.io/badge/verified-microservices.io%2Fftgo-brightgreen)](https://github.com/microservices-patterns/ftgo-application)
[![Status: internal beta](https://img.shields.io/badge/status-internal_beta-orange)]()

> **Status — internal beta.** Use freely on real Java repos; expect rough edges. See [`docs/release-readiness-checklist.md`](./docs/release-readiness-checklist.md) for what must land before this is recommended for unsupervised enterprise-wide rollout (notably: domain-safe source matching for duplicate class names, chunk-and-merge for very large domains, stronger end-to-end verification, and multi-repo orchestration).

---

## The problem this solves

In a typical enterprise Java shop:

- A developer has **~300 GitHub Copilot premium requests per month**.
- The repo has 50–200 business features spread across Controller → Service → DAO → DB.
- Every time the developer asks Copilot *"how does the Invoice Compare feature work?"* or *"add a new status to File Delivery"*, Copilot has **no persistent context**. The dev re-types it. Or Copilot guesses, gets it wrong, and the dev iterates — burning premium requests on inaccurate answers.

Across many features × many developers, this is a **major productivity tax**. Most of those premium calls are spent re-explaining the same domain knowledge over and over.

**Skills** — small, accurate, AI-readable instruction files (one `SKILL.md` per business feature, committed to your repo) — solve this. Once a skill exists, Copilot and Claude read it automatically and start every conversation with accurate feature context. **No re-explaining. Fewer iterations. Premium requests go further.**

This repo contains **the agent that generates and maintains those skill files** for you.

---

## What you get

| Without skills | With skills (this agent) |
|---|---|
| Copilot re-discovers your domain on every prompt | Copilot starts with the feature's full context already loaded |
| 5–8 premium calls per feature question (back-and-forth) | 1 premium call, correct answer first time |
| New hires take weeks to learn each feature | New hires read the SKILL.md and start contributing |
| Copilot hallucinates status enums, wrong endpoint paths, wrong DTO fields | Copilot cites the actual `ClassName.methodName()` for every rule |
| You re-explain the FileDelivery state machine to Copilot 47 times a month | You explain it once — to the agent, which writes the skill |

---

## How it works

The agent is **host-agent-driven**: the Python tool walks the repo, builds prompts, and parses responses — but it never makes outbound API calls. The LLM reasoning happens inside whatever AI session you already use (Claude Code, Codex, GitHub Copilot Chat, Claude Cowork), so it costs nothing beyond the subscription you already pay for.

Each LLM-dependent stage has two halves: `*-emit` writes a prompt file, you paste it into your AI session, save the response, and `*-ingest` turns the response into the canonical artifact.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        FIRST RUN (one-time)                          │
│                                                                      │
│  Stage 1: Crawl            (zero LLM turns — pure local parsing)     │
│  Stage 2: Plan             (plan-emit  →  AI session  →  plan-ingest)│
│  Stage 3: Generate         (generate-emit  →  AI session  →  ingest) │
│  Stage 4: Link             (link-emit  →  AI session  →  link-ingest)│
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                  ┌─────────────────────────────────┐
                  │  .github/skills/                │
                  │  ├── order-management/SKILL.md  │
                  │  ├── consumer-management/...    │
                  │  └── delivery-management/...    │
                  └─────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  PHASE 2 — INCREMENTAL UPDATES                       │
│                                                                      │
│  On every PR merge or local change:                                  │
│    git diff → map changed files to feature → update-emit             │
│    → AI session generates updated SKILL.md → update-ingest           │
│    → bump version → commit                                           │
└──────────────────────────────────────────────────────────────────────┘
```

**Why this shape?** The Python tool is fully deterministic — file walking, parsing, source assembly, response application. The host AI agent does the reasoning. Nothing in this repo talks to the network; nothing requires an API key.

For a visual sequence diagram of the IDE-side developer experience — from typing *"analyze this project"* through committed SKILL.md files — see [`docs/agent-invocation-flow.md`](./docs/agent-invocation-flow.md). For enterprise rollout guidance across VS Code, IntelliJ, Copilot, Claude, and Codex, see [`docs/enterprise-agent-selection-guide.md`](./docs/enterprise-agent-selection-guide.md).

### Enterprise agent selection

The tool itself has no model setting. The selected host AI session supplies the reasoning, so teams can run the same emit/ingest workflow from Claude, Codex, Copilot Chat, or another approved IDE assistant.

For most enterprise teams:

| Workload | Recommended host session |
|---|---|
| First run on an unknown or legacy repo | Strongest available reasoning session, such as Claude Opus-class or Codex high-reasoning |
| First run on a clean Spring Boot service | Claude Sonnet-class, Codex, or another capable approved session |
| Incremental update for one reviewed feature | Sonnet-class, Codex, or Copilot Chat |
| Everyday feature questions after skills are committed | GitHub Copilot Chat in VS Code/IntelliJ, Claude, or Codex reading `.github/skills` |

The recommended operating model is centralized: repo owners or feature leads spend the initial generation turns once, commit the generated skills, and let every developer benefit from the shared feature context during daily work.

---

## Quick start

### Prerequisites

- Python 3.10+ (`python3 --version`)
- An AI session you already use — **any of**: Claude Code, GitHub Copilot Chat, Codex, Claude Cowork
- The Java repo you want to document, checked out locally

**No API keys. No third-party Python dependencies. No outbound network calls.**

### Install

```bash
git clone https://github.com/bipinhcs11/Customized_Agent_For_Developer.git
cd Customized_Agent_For_Developer
# That's it.
```

### Not sure if it'll work on your repo? Run `doctor` first

```bash
python3 -m tools.skill_generator.cli doctor /path/to/your/repo
```

A 30-second look at your repo before you commit to anything. Shows class count, detected framework, oversized files, and how long the full pipeline will take. No AI turns, nothing written to disk. See [`docs/skill-gen-doctor.md`](./docs/skill-gen-doctor.md) for an example.

### Run the pipeline

Each LLM stage is two commands with a paste in between. Stage 1 (Crawl) has no LLM step — it just walks the repo.

```bash
TARGET=/path/to/your/java/repo

# Stage 1 — fast, deterministic, no AI
python3 -m tools.skill_generator.cli crawl "$TARGET" \
    --output "$TARGET/.skill-gen/.index.json"

# Stage 2 — Plan
python3 -m tools.skill_generator.cli plan-emit "$TARGET/.skill-gen/.index.json"
# Open .skill-gen/plan-prompt.md, paste it into your AI session.
# Save the response as .skill-gen/plan-response.md.
python3 -m tools.skill_generator.cli plan-ingest "$TARGET/.skill-gen/plan-response.md"

# Stage 3 — Generate (one prompt per domain)
python3 -m tools.skill_generator.cli generate-emit \
    "$TARGET/.skill-gen/.plan.json" --repo "$TARGET"
# For each .skill-gen/.generate-prompts/<domain>.md, paste into the AI session.
# Save each response as .skill-gen/.generate-responses/<domain>.md.
python3 -m tools.skill_generator.cli generate-ingest \
    "$TARGET/.skill-gen/.plan.json" --repo "$TARGET"

# Stage 4 — Link
python3 -m tools.skill_generator.cli link-emit "$TARGET/.github/skills"
# Paste link-prompt.md, save response as link-response.md.
python3 -m tools.skill_generator.cli link-ingest \
    "$TARGET/.skill-gen/link-response.md" --skills-dir "$TARGET/.github/skills"
```

The final SKILL.md files land in `<your-repo>/.github/skills/<domain-id>/SKILL.md`. Intermediate prompts and responses live under `<your-repo>/.skill-gen/`.

### Why the emit/ingest dance?

The whole point of the agent is to **stop spending premium-request budget**. Calling Anthropic from a Python script would mean adding *another* cost line that competes with your subscription. By emitting prompt files and ingesting responses, the LLM turns happen inside your existing Claude Code / Copilot / Codex session — no separate API spend, no separate key to manage.

### Phase 2 — incremental updates

After the first run commits the skills to your repo, refresh them when code changes:

```bash
python3 -m tools.skill_generator.cli update-emit --repo .
# Paste each .skill-gen/.update-prompts/<feature>.md into your AI session.
# Save each response as .skill-gen/.update-responses/<feature>.md.
python3 -m tools.skill_generator.cli update-ingest --repo . --commit
```

The same emit/ingest pattern; the same zero-API-call guarantee.

---

## What a generated SKILL.md looks like

Here's a fragment from the **Data Flow** section of `consumer-management/SKILL.md`, generated from the FTGO microservices reference application:

```
POST /consumers
   |
   v
ConsumerController.create(CreateConsumerRequest)
   |   request.getName() -> PersonName
   v
ConsumerService.create(name)                        @Transactional
   |
   |-- Consumer.create(name)                         <- builds aggregate + ConsumerCreated event list
   |
   |-- consumerRepository.save(rwe.result)           -> Consumer DB (JPA, MySQL)
   |
   |__ domainEventPublisher.publish(Consumer.class, id, rwe.events)
              -> Eventuate Tram outbox -> Kafka topic net.chrisrichardson...Consumer
              + emit ConsumerCreated domain event

@KafkaListener (Tram saga dispatch on channel "consumerService")
   |
   v
ConsumerServiceCommandHandlers.commandHandlers()
   |-- onMessage(ValidateOrderByConsumer.class)
           |__ ConsumerService.validateOrderForConsumer(consumerId, orderTotal)
                   |__ Consumer.validateOrderByConsumer(orderTotal)
                           <- spend rule on the aggregate; throws ConsumerVerificationFailedException
```

The skill captures the **async semantics** (`@Async`, `.get() <- blocks`), **DB destinations** (`-> Consumer DB`), **Kafka topic names**, **exception flow**, and **side effects** (`+ emit ConsumerCreated`). When Copilot reads this, it knows enough to safely modify `validateOrderForConsumer()` without breaking the saga reply contract.

See `verification-output/ftgo-skills/` in this repo for two complete SKILL.mds generated from the real FTGO codebase — one for `consumer-management` (19 classes) and one for `accounting-authorization` (27 classes), with cross-domain saga relationships linked between them.

---

## Verified on a real microservices repo

This agent was end-to-end verified against [microservices-patterns/ftgo-application](https://github.com/microservices-patterns/ftgo-application) — Chris Richardson's reference Spring Boot microservices app.

| Metric | Value |
|---|---|
| Classes parsed | 358 |
| Lines of code analyzed | 15,714 |
| Microservice modules | 12 |
| Domains identified by Stage 2 | 9 (one per microservice, mapped 1:1) |
| Confidence (most domains) | HIGH |
| Host-agent turns total | ~11 (1 plan + 9 generate + 1 link) |
| Schema conformance | 12/12 frontmatter fields, 12/12 body sections, 0 Java code blocks in body |
| Warnings | 0 |

Full details in [`verification-output/VERIFICATION_REPORT.md`](./verification-output/VERIFICATION_REPORT.md). The verification used an earlier API-call architecture; the prompts and outputs are unchanged — only the delivery mechanism (host agent vs. API) is different.

---

## Supported Java flavors

The agent works on **any flavor of Java repo**, not just modern Spring Boot. It auto-detects which it is and writes skills that describe whatever the target repo actually uses:

| Flavor | Detected by |
|---|---|
| Spring Boot 2.x / 3.x | `@SpringBootApplication` + annotation-driven REST |
| Spring MVC | XML wiring or annotation, no `@SpringBootApplication` |
| Struts 1 / 2 | `struts-config.xml` action mappings |
| Quarkus | `@Path` annotations without `@RestController` |
| Spring Batch | `@EnableBatchProcessing` or `<job>` elements |
| Quartz Scheduler | `quartz*.xml` with cron expressions |
| Raw servlets | `web.xml` URL patterns |
| Legacy hybrid | `.sql` stored procedures + `.sh` orchestration + Java |
| Mixed-stack | Multiple of the above in one repo |

For legacy apps, the crawler also reads stored procedures (`.sql`), shell scripts (`.sh`), Flyway/Liquibase migrations, and Spring Batch job XML — so a feature that lives half in Java and half in a stored proc is documented as one cohesive skill.

---

## Cost model

The pipeline is **free to operate** — every LLM turn runs inside a session you already pay for.

| Stage | Host-agent turns | What happens |
|---|---|---|
| Crawl | 0 | Pure local parsing |
| Plan | 1 | One paste-and-respond cycle |
| Generate | 1 per detected domain | Each skill is one focused turn |
| Link | 1 | One turn covers all cross-references |
| **First run total** | **~12–15 turns for a 10-domain repo** | Roughly linear in domain count |
| **Phase 2 update** | **1–2 turns per PR** | Only changed features re-generate |

Compare to the alternative without skills: a developer asks 5 feature questions a day × 200 working days × 10 developers × ~3 premium calls per question due to context misses = **~30,000 premium requests/year per team** spent on context re-discovery. With skills in place, those same 5 questions a day land correctly on the first try — and the skills themselves cost zero subscription dollars to produce.

---

## Project layout

```
.
├── README.md                          ← This file
├── AGENT.md                           ← Full pipeline specification
├── CLAUDE.md                          ← Cowork / Claude Code project config
├── OPUS_PROMPT.md                     ← Original problem statement
├── .github/
│   └── copilot-instructions.md        ← Tells Copilot to read skills before answering
│
├── tools/
│   └── skill_generator/               ← THE AGENT (Python, stdlib only)
│       ├── cli.py                     ← CLI entry point (emit/ingest subcommands)
│       ├── crawler.py                 ← Stage 1 (zero LLM turns)
│       ├── prompts.py                 ← All prompt strings (single source of truth)
│       ├── plan.py                    ← Stage 2 (emit_prompt / ingest_response)
│       ├── generate.py                ← Stage 3 (per-domain emit / ingest)
│       ├── link.py                    ← Stage 4 (emit_prompt / ingest_response)
│       ├── update.py                  ← Phase 2 incremental updater
│       ├── validate.py                ← artifact-3 contract checker (used by ingest + `skill-gen validate`)
│       ├── doctor.py                  ← `skill-gen doctor` — pre-flight repo report
│       └── README.md                  ← Internal module docs
│
├── skills/                            ← Reference skills (the quality bar)
│   ├── file-delivery/SKILL.md
│   ├── invoice-compare/SKILL.md
│   ├── payment-method-determination/SKILL.md
│   └── skill-generator/
│       └── references/
│           └── data-flow-example.md   ← Pattern for the rich Data Flow section
│
├── examples/                          ← Reference Java code (illustrative only)
│   ├── file-delivery/                 ← Spring Boot controller/service/dao/sql
│   ├── invoice-compare/
│   ├── payment-method-determination/
│   └── legacy-forward-generator/      ← Historical: old code-gen templates
│
├── verification-output/               ← Proof the agent works end-to-end
│   ├── VERIFICATION_REPORT.md
│   ├── ftgo-crawl-index.json
│   ├── ftgo-plan.json
│   └── ftgo-skills/
│       ├── consumer-management-SKILL.md
│       ├── consumer-management-SKILL-v2-rich-dataflow.md
│       ├── accounting-authorization-SKILL.md
│       └── cross-domain-links.json
│
└── docs/
    └── design-history/                ← Design notes for contributors
        └── CODEX_REVIEW_PROMPT.md
```

---

## How GitHub Copilot uses the generated skills

After your first run, your target repo has a `.github/skills/<domain-id>/SKILL.md` for each feature and a `.github/copilot-instructions.md` that tells Copilot **to read those skills before answering**.

Example developer interaction:

> **Developer:** "Add a new `ARCHIVED` status to File Delivery"
>
> **Copilot (reading `file-delivery/SKILL.md` automatically):** I see the current `FileDeliveryStatus` enum has PENDING, SCANNING, READY, DELIVERED, ACKNOWLEDGED, SCAN_FAILED, EXPIRED, DELETED. The skill notes that `isDeliverable()` returns true only for READY, and `isTerminal()` returns true for SCAN_FAILED, EXPIRED, DELETED. To add ARCHIVED:
> 1. Add to `FileDeliveryStatus` enum
> 2. Add to `isTerminal()` if archived files should be excluded from delivery flow
> 3. Add a migration: `ALTER TABLE file_delivery ALTER COLUMN status SET DEFAULT 'PENDING';` (the VARCHAR allows the new value)
> 4. Update `idx_file_delivery_status` if filtering archived rows needs an index

That answer is correct, complete, and arrived in **one prompt** — because Copilot read the skill before responding. Without the skill, that same answer takes 5–8 back-and-forth prompts to assemble.

---

## Configuration

The agent's defaults work for most repos. Override via CLI flags:

| Flag | Default | What it does |
|---|---|---|
| `--output` / `-o` | varies by subcommand | Where to write the prompt / artifact |
| `--output-dir` | `<repo>/.github/skills/` | Where SKILL.mds land (generate-ingest) |
| `--prompts-dir` | `<repo>/.skill-gen/.generate-prompts/` | Where per-domain emit prompts land |
| `--responses-dir` | `<repo>/.skill-gen/.generate-responses/` | Where to look for per-domain responses |
| `--exclude` | (see `crawler.py`) | Additional directories to skip in crawl |
| `--skip-tests` | off | Exclude `*Test.java` and `/test/` paths |
| `--force` | off | Overwrite an existing SKILL.md on ingest |
| `--only DOMAIN_ID` | (all) | Restrict emit/ingest to one domain |
| `--commit` | off | (update-ingest) git-add + commit the refreshed SKILL.mds |

---

## What this is NOT

So nobody starts with the wrong expectation:

- **Not a forward code generator.** "Given a feature name, write Controller + Service + DAO + DDL" is not the job. The agent reads existing code and writes instruction files about it.
- **Not a documentation generator for human readers.** The output is AI-readable. Tables and cited rules are tuned for AI consumption, not human reading flow.
- **Not tied to specific business domains.** The three sample skills in `skills/` (File Delivery / Invoice Compare / Payment Method Determination) are *illustrations of the format*, not the agent's deliverable set. The agent ships for whatever features exist in whatever repo you point it at.

---

## Roadmap

What's in v0.3 (now):

- All four pipeline stages working end-to-end via emit/ingest
- Phase 2 incremental updater (git-diff-based)
- Crawler handles Java + XML + properties + YAML + SQL + shell
- Python CLI with `crawl / plan-emit / plan-ingest / generate-emit / generate-ingest / link-emit / link-ingest / update-emit / update-ingest`
- **Zero outbound network calls; no API key required**
- Verified end-to-end against FTGO microservices reference (under earlier API architecture; prompts unchanged)

What's coming next:

- **Multi-repo orchestration** — config-driven runs across 50+ enterprise repos in one pass
- **Chunk-and-merge for very large domains** — Stage 3 currently truncates domains > 24KB of source; real chunk-merge needs implementation
- **Real Java AST parsing** — optional `javalang` dependency to replace the regex parser for edge cases (Lombok, annotation processors)
- **Web UI for plan review** — instead of editing `plan.json` by hand, click-to-approve domains in a browser before Stage 3 runs

---

## FAQ

**Does this require an Anthropic API key?**
No. The tool never makes outbound network calls. Every LLM turn happens inside an AI session you already use (Claude Code, GitHub Copilot Chat, Codex, Claude Cowork). The cost to operate the agent is your normal subscription — nothing extra.

**Will this work on my legacy monolith with stored procedures and shell scripts?**
Yes — the crawler reads `.sql`, `.sh`, Flyway/Liquibase migrations, and Spring Batch job XML alongside Java. The generated SKILL.md describes whatever the target repo actually uses.

**Does it generate Java code?**
No. The agent emits SKILL.md instruction files. Java code generation tools can *consume* these skills as input (and produce better code because of it), but that's downstream of this agent's job.

**What if my Java is parsed badly?**
The crawler is regex-based, which is fast and dependency-free but has edge cases (Lombok-generated code, exotic generics). For most repos it works fine. If accuracy matters more than speed, a future version will use `javalang` for full AST parsing.

**How do I review the plan before Stage 3 runs?**
You always do — the emit/ingest split makes plan review the default. After `plan-ingest` writes `plan.json`, edit the `domains[]` array (remove domains you don't want, rename ids, merge domains) before running `generate-emit`. No way to skip review even if you wanted to.

**What if my repo has 5000 classes?**
The Plan stage's prompt scales with index size. At ~5000 classes the index is ~500KB — still within Claude's context window but worth chunking. Workaround for now: run the crawler on subdirectories separately and merge plans manually. Multi-pass planning is on the roadmap.

**Can I customize the SKILL.md format?**
The format is defined in `tools/skill_generator/prompts.py`. Edit `STAGE_3_GENERATE_PROMPT` to change what sections appear or what each one requires. The default is the artifact-3 standard from this project's design history.

---

## Contributing

The agent's prompts are the load-bearing part. If you find the generated SKILL.mds are missing something, or you have a richer pattern from your own enterprise (like the rich Data Flow style in `skills/skill-generator/references/data-flow-example.md`), the highest-impact contribution is sharpening the prompts in `tools/skill_generator/prompts.py`.

The Python is intentionally stdlib-only and ~1500 lines total — easy to audit, modify, and extend.

For the rationale behind the design decisions, see `OPUS_PROMPT.md` (original problem statement) and `docs/design-history/CODEX_REVIEW_PROMPT.md` (cross-model design review).

---

## License

MIT — see [`LICENSE`](./LICENSE) at the repo root.

---

## Acknowledgments

Design informed by Chris Richardson's [microservices.io](https://microservices.io) reference apps and patterns. End-to-end verification ran against [`ftgo-application`](https://github.com/microservices-patterns/ftgo-application). The SKILL.md schema and pipeline shape were prototyped across multiple Claude conversations summarized in `OPUS_PROMPT.md`.
