# FeatureBased Skill Generator Agent

> **Turn any Java repo into AI-readable instruction files — once — so GitHub Copilot and Claude answer feature questions correctly the first time, every time, without burning your premium-request budget.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Stage 1: zero AI calls](https://img.shields.io/badge/Stage_1-zero_AI_calls-green)]()
[![Verified on FTGO](https://img.shields.io/badge/verified-microservices.io%2Fftgo-brightgreen)](https://github.com/microservices-patterns/ftgo-application)

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

The agent runs as a **four-stage pipeline** plus an incremental updater:

```
┌──────────────────────────────────────────────────────────────────────┐
│                        FIRST RUN (one-time)                          │
│                                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐        │
│  │ Stage 1  │    │ Stage 2  │    │ Stage 3  │    │ Stage 4  │        │
│  │  Crawl   │ →  │   Plan   │ →  │ Generate │ →  │   Link   │        │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘        │
│  Zero AI calls   1 AI call       1 per domain    1 AI call           │
│  walks repo      Claude groups   writes one      finds cross-        │
│  locally         classes into    SKILL.md per    domain links        │
│                  domains         domain                              │
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
│  On every PR merge:                                                  │
│    git diff → map changed files to feature → re-run Stage 3 only     │
│    for affected features → bump version → commit                     │
└──────────────────────────────────────────────────────────────────────┘
```

**Why this shape?** The expensive parts (file walking, parsing) are free. The AI calls are tightly scoped: one to identify domains, one per domain to write the skill, one to find cross-references. Steady-state cost after the first run is **1–2 AI calls per PR**.

---

## Quick start

### Prerequisites

- Python 3.10+ (`python3 --version`)
- An Anthropic API key (`ANTHROPIC_API_KEY`)
- The Java repo you want to document, checked out locally

No third-party Python dependencies — the agent uses only the standard library.

### Install

```bash
git clone https://github.com/bipinhcs11/Customized_Agent_For_Developer.git
cd Customized_Agent_For_Developer
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Run end-to-end on your Java repo

```bash
# Replace /path/to/your/java/repo with your actual target
python3 -m tools.skill_generator.cli run-all /path/to/your/java/repo
```

That command runs all four stages in order. The output lands in `<your-repo>/.github/skills/<domain-id>/SKILL.md`.

### Or run stage-by-stage (recommended for the first run)

```bash
# Stage 1 — free, fast, deterministic
python3 -m tools.skill_generator.cli crawl /path/to/repo --output index.json

# Stage 2 — one AI call, review the plan before generating
python3 -m tools.skill_generator.cli plan index.json --output plan.json

# Stage 3 — generates one SKILL.md per domain (rate-limited, checkpointed)
python3 -m tools.skill_generator.cli generate plan.json --repo /path/to/repo

# Stage 4 — adds cross-domain relationships
python3 -m tools.skill_generator.cli link /path/to/repo/.github/skills
```

### Dry-run mode (no API spend)

Every AI-dependent subcommand supports `--dry-run`:

```bash
python3 -m tools.skill_generator.cli plan index.json --dry-run
# Prints the prompt that would be sent; returns a placeholder response
```

### Phase 2 — automatic updates

After your first run commits the skills to your repo, add this GitHub Action so skills auto-refresh on every PR merge:

```yaml
# .github/workflows/refresh-skills.yml
name: Refresh Skills
on:
  push:
    branches: [main]
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 2 }
      - uses: actions/setup-python@v5
        with: { python-version: '3.10' }
      - run: python3 -m tools.skill_generator.cli update --repo . --commit
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

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
| AI calls total | ~11 (1 plan + 9 generate + 1 link) |
| Schema conformance | 12/12 frontmatter fields, 12/12 body sections, 0 Java code blocks in body |
| Warnings | 0 |

Full details in [`verification-output/VERIFICATION_REPORT.md`](./verification-output/VERIFICATION_REPORT.md).

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

## Token economics

The pipeline is designed to be **cheap to operate at enterprise scale**.

| Stage | AI calls per run | Why |
|---|---|---|
| Crawl | 0 | Pure local parsing |
| Plan | 1 | One call covers the whole repo |
| Generate | 1 per detected domain | Each skill is one focused call |
| Link | 1 | One call covers all cross-references |
| **First run total** | **~12–15 calls for a 10-domain repo** | Roughly linear in domain count |
| **Phase 2 update** | **1–2 calls per PR** | Only changed features re-generate |

Compare to the alternative: a developer asks 5 feature questions a day × 200 working days × 10 developers × ~3 premium calls per question due to context misses = **~30,000 premium requests/year per team** spent on context re-discovery. With skills in place, those same 5 questions a day land correctly on the first try.

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
│       ├── cli.py                     ← CLI entry point
│       ├── crawler.py                 ← Stage 1 (zero AI calls)
│       ├── claude_client.py           ← Stdlib HTTP client for Claude API
│       ├── prompts.py                 ← All prompt strings (single source of truth)
│       ├── plan.py                    ← Stage 2
│       ├── generate.py                ← Stage 3 (rate-limited, checkpointed)
│       ├── link.py                    ← Stage 4
│       ├── update.py                  ← Phase 2 incremental updater
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
| `--model` | `claude-sonnet-4-20250514` | Pin a specific Claude model |
| `--output-dir` | `<repo>/.github/skills/` | Where SKILL.mds land |
| `--exclude` | (see `crawler.py`) | Additional directories to skip in crawl |
| `--skip-tests` | off | Exclude `*Test.java` and `/test/` paths |
| `--force` | off | Regenerate even if SKILL.md exists |
| `--only DOMAIN_ID` | (all) | Generate just one domain |
| `--dry-run` | off | Print the prompt; don't call the API |

---

## What this is NOT

So nobody starts with the wrong expectation:

- **Not a forward code generator.** "Given a feature name, write Controller + Service + DAO + DDL" is not the job. The agent reads existing code and writes instruction files about it.
- **Not a documentation generator for human readers.** The output is AI-readable. Tables and cited rules are tuned for AI consumption, not human reading flow.
- **Not tied to specific business domains.** The three sample skills in `skills/` (File Delivery / Invoice Compare / Payment Method Determination) are *illustrations of the format*, not the agent's deliverable set. The agent ships for whatever features exist in whatever repo you point it at.

---

## Roadmap

What's in v0.2 (now):

- All four pipeline stages working end-to-end
- Phase 2 incremental updater (git-diff-based)
- Crawler handles Java + XML + properties + YAML + SQL + shell
- Python CLI with `crawl / plan / generate / link / update / run-all`
- Verified against FTGO microservices reference

What's coming next:

- **Multi-repo orchestration** — `skill-gen generate-all --config agent-config.yml` across 50+ enterprise repos in one pass
- **Chunk-and-merge for very large domains** — Stage 3 currently truncates domains > 24KB of source; real chunk-merge needs implementation
- **Claude skill twin** — a markdown skill at `skills/skill-generator/SKILL.md` that lets Claude in Cowork or Copilot Chat execute the same pipeline without the Python CLI (for developers who can't install Python locally)
- **Real Java AST parsing** — optional `javalang` dependency to replace the regex parser for edge cases (Lombok, annotation processors)
- **Web UI for plan review** — instead of editing `plan.json` by hand, click-to-approve domains in a browser before Stage 3 runs

---

## FAQ

**Does this require a paid Claude account?**
Yes — you need an `ANTHROPIC_API_KEY`. Stage 1 (crawl) runs without one; Stages 2–4 are AI calls. For a typical 10-domain repo the first run costs a few dollars; incremental updates are pennies per PR.

**Will this work on my legacy monolith with stored procedures and shell scripts?**
Yes — the crawler reads `.sql`, `.sh`, Flyway/Liquibase migrations, and Spring Batch job XML alongside Java. The generated SKILL.md describes whatever the target repo actually uses.

**Does it generate Java code?**
No. The agent emits SKILL.md instruction files. Java code generation tools can *consume* these skills as input (and produce better code because of it), but that's downstream of this agent's job.

**What if my Java is parsed badly?**
The crawler is regex-based, which is fast and dependency-free but has edge cases (Lombok-generated code, exotic generics). For most repos it works fine. If accuracy matters more than speed, a future version will use `javalang` for full AST parsing.

**How do I review the plan before Stage 3 runs?**
Run stage-by-stage. After `skill-gen plan`, open `plan.json`, edit the `domains[]` array (remove domains you don't want, rename ids, merge domains), then run `skill-gen generate plan.json --repo .`. Or use `run-all` and trust the planner — it's been right on every test repo so far.

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

This project does not yet have a license file. Before publishing for wider use, add one:
- **MIT** for permissive use (most common for developer tools)
- **Apache 2.0** for patent grant in addition to permissive use
- **Closed / proprietary** if your enterprise restricts redistribution

Once chosen, drop a `LICENSE` file at the repo root.

---

## Acknowledgments

Design informed by Chris Richardson's [microservices.io](https://microservices.io) reference apps and patterns. End-to-end verification ran against [`ftgo-application`](https://github.com/microservices-patterns/ftgo-application). The SKILL.md schema and pipeline shape were prototyped across multiple Claude conversations summarized in `OPUS_PROMPT.md`.
