# Design Review: Custom Agent that Generates Per-Feature Skill Files for Java Enterprise Repos

> **Historical document.** This is an early-stage design-review prompt used to stress-test the original concept. The shipped implementation differs from this brief in one important respect: the agent is now **host-agent-driven** (emits prompt files, ingests responses inside the developer's existing AI session) rather than calling Anthropic directly. See `AGENT.md` and `README.md` for the current architecture.

You are a senior software architect. The user is designing a custom AI agent for an enterprise development team. Your job is to **validate the design and surface anything wrong, unclear, or unrealistic before they start building**. Do not write code. Do not invent requirements. Push back on anything in this brief that you find dubious.

---

## The Problem Being Solved

In enterprise Java development:

- A typical engineer has a small monthly GitHub Copilot premium-request budget (≈300 requests/month).
- Repos are large — often 50–200 business features spread across Controller → Service → DAO → DAO Impl → DB schema, sometimes with stored procedures and shell scripts mixed in.
- Every time the engineer asks Copilot "how does the Invoice Compare feature work?" or "add a new status to File Delivery", Copilot has no persistent context. The engineer re-types the context. Or Copilot guesses, gets it wrong, and the engineer iterates — burning premium requests on inaccurate answers.
- Across many repos and many engineers, this is a major productivity tax.

**Skills** — small, accurate, AI-readable instruction files (a SKILL.md per business feature) committed to the repo — solve this. Once a skill exists, Copilot and Claude read it automatically and start every conversation with accurate feature context. No re-explaining. Fewer iterations. Premium requests go further.

The thing being built is the **agent that generates and maintains those skill files**.

---

## The Product

A custom agent that:

1. Is pointed at an arbitrary existing Java enterprise codebase by a developer.
2. **First run** (expensive): deep-scans the repo, identifies business features, writes one SKILL.md per feature, commits them to the repo.
3. **Subsequent runs** (cheap, incremental): detects which features had code changes via `git diff`, refreshes only those skills, commits the updates.
4. Once skills exist, Copilot and Claude pick them up automatically via the standard skill-loading conventions (`.github/copilot-instructions.md`, `skills/*/SKILL.md`).

The agent **emits instruction files, not Java code**. Plenty of tools already do forward code generation; this is not another one. Existing forward-generation tooling can consume these skills as input — that's a downstream benefit, not the agent's job.

---

## What "Any Java Repo" Means

The agent must handle, at minimum, all of the following — and detect at runtime which one the target repo is:

- **Spring Boot 2.x / 3.x** — annotation-driven REST + Spring Data JPA microservices
- **Spring MVC** — annotation or XML wiring
- **Struts 1 and Struts 2** — XML action mappings
- **Quarkus** — JAX-RS annotations
- **Spring Batch** — Job / Step / Processor configurations
- **Quartz Scheduler** — cron-driven jobs
- **Raw servlets** — `web.xml` URL patterns
- **Legacy hybrid applications** — a mix of Java classes, **stored procedures (`.sql`)**, **shell scripts (`.sh`)**, DDL files, Hibernate `.hbm.xml`, XML-wired Spring beans, and sometimes integration points to older systems
- **Mixed-stack repos** with multiple of the above in one codebase

A "business feature" is whatever logical unit makes sense in *that* codebase:
- a Spring `@RestController` plus its service/dao chain in a microservice,
- a Spring Batch `Job` in a batch app,
- a stored procedure called from a Java DAO in a legacy app,
- a Quartz cron job that runs a `Processor` class.

The agent must detect feature boundaries from whatever signals exist: annotations, package layout, XML action mappings, bean wiring, file naming conventions, SQL invocation sites, and shell scripts that orchestrate Java jobs.

---

## File Types the Agent Must Crawl

| Type | Purpose |
|---|---|
| `*.java` | Class names, packages, annotations, method names, extends/implements |
| `web.xml` | Servlet classes and URL patterns |
| `struts-config.xml` | Action paths and action classes |
| Spring `applicationContext*.xml` | Bean ids and classes (XML wiring) |
| `hibernate.cfg.xml`, `*.hbm.xml` | Mapped classes and tables |
| `persistence.xml` | JPA entity classes |
| `quartz*.xml` and Spring Batch job XML | Job classes and cron expressions |
| `*.sql` | Stored procedures, DDL, DB migration files (Flyway/Liquibase) |
| `*.sh` | Shell scripts (often orchestrate Java jobs or load data in legacy apps) |
| `*.properties`, `*.yml`, `*.yaml` | Config keys (datasource, mail, file, batch, queue, scheduler) |
| `pom.xml`, `build.gradle` | Java version, dependencies, modules |

Excluded: `target/`, `build/`, `.git/`, `.mvn/`, `generated/`, files with `@Generated` or `// DO NOT EDIT` markers, binary files (`.class`, `.jar`, `.war`, etc.).

---

## The Pipeline (High Level)

The proposed design is a four-stage pipeline. Stage 1 spends zero tokens; the rest are deliberately scoped to keep the AI bill small.

### Stage 1 — Crawl (zero AI calls)
Walk the repo locally. Parse every relevant file. Emit a single JSON index describing every class, XML signal, stored procedure, shell script, and config key found. No AI involvement.

### Stage 2 — Plan (one AI call)
Send the index to Claude with grouping rules:
- Primary signal: package name
- Secondary: class name prefix
- Tertiary: annotations + XML mappings
- God classes (e.g. >300 lines) flagged for splitting
- Deprecated classes flagged and kept; generated classes excluded
- Shared utilities used by 3+ domains assigned to `shared-infrastructure`
- Spring XML beans assigned to the Java class they reference
- Struts actions assigned to the domain of the service they call
- Quartz/Batch jobs become one domain per distinct Job

Output: a JSON `domains[]` array. The developer reviews in their IDE, toggles, merges, renames, and confirms before Stage 3 runs.

### Stage 3 — Generate (one AI call per approved domain, rate-limited)
For each approved domain:
- Collect the full source of all files in the domain.
- Include relevant XML excerpts and config key-value pairs.
- If the source exceeds the token budget, chunk at method boundaries and merge partial outputs.
- Wait between calls. Exponential backoff on HTTP 429. Pause queue after 3 consecutive 429s.
- Save a checkpoint after each domain. On restart, skip already-completed domains.

Output: one SKILL.md per domain.

### Stage 4 — Link (one AI call)
Read a short summary of each generated SKILL.md and ask Claude to identify cross-domain dependencies: direct class calls, shared DAOs, exceptions thrown in one domain caught in another, shared config. Append each link to the `related_skills` frontmatter and the Related Skills body section in both SKILL.mds.

**Total tokens for a 10-domain repo: roughly 12–15 AI calls.** Stage 1 (the heaviest work) is free.

---

## SKILL.md Output Format

A previously-drafted standard defines the schema. Frontmatter (all required):

```
---
skill: [Title Case feature name]
domain: [kebab-case-id]
version: [integer, starts at 1, increments on every update]
project_type: [REST API | Batch Job | Scheduled | Hybrid | Monolith Module]
framework: [Spring Boot | Struts | Spring MVC | Quarkus | Raw Servlet | Unknown]
java_version: [8 | 11 | 17 | 21 | Unknown]
legacy: [true | false]
status: [active | deprecated | migrating]
flags: [comma-separated: deprecated | god_class_split | xml_driven | batch | shared | no_tests | partial]
related_skills: [comma-separated domain-ids, or none]
generated_by: [skill_generator.agent | human | hybrid]
last_updated: [YYYY-MM-DD]
---
```

Body sections in this exact order, none omitted (empty sections write the literal string `none found`):

1. **Purpose** — 2–3 sentences, business value only
2. **Entry Points** — every way the feature is triggered, each citing `ClassName.methodName()`
3. **Business Logic** — three subsections: Core Flow (numbered steps), Validation Rules, Business Rules
4. **Key Classes & Files** — table of every file belonging to the domain
5. **Data Flow** — ASCII flow from input to output
6. **Database & Storage** — tables, file paths, queues, cache keys
7. **External Dependencies** — services, APIs, message brokers
8. **Error Handling** — table of every exception, trigger, and handling
9. **Edge Cases** — defensive code found in the source, with citations
10. **Legacy Notes** — deprecated markers, TODO comments, migration hints
11. **Related Skills** — cross-domain dependencies
12. **AI Agent Instructions** — specific, non-generic rules for any AI editing this feature

### One Open Tension I Want Your Opinion On

The schema as drafted says **"no Java code blocks in the body — tables and cited rules only"**. Strict interpretation.

But the goal of the skills is that an AI (Copilot or Claude) reads them and produces code that matches the existing feature. Concrete code patterns (status enum definitions with their helper methods, controller endpoint signatures, validator predicates, DDL fragments) are arguably the highest-signal content for an AI to pattern-match against.

Pure "tables + cited rules" forces the AI to *infer* patterns from prose like "Status lifecycle: PENDING → SCANNING → READY — see FileDeliveryStatus enum", rather than letting it *copy* a pattern it can see.

**Question: should the schema be relaxed to allow code blocks where they carry signal no table can?** What's the tradeoff? When does each form win?

---

## Phase 2 — Incremental Maintenance

After the first run, the agent must keep skills current automatically. Triggers, in preference order:

1. **GitHub Action on PR merge** — preferred for enterprise; skills are never stale on `main`.
2. **Git pre-commit hook** — lightweight local check.
3. **File watcher** — real-time during local development.
4. **Manual CLI command** — `skill-gen update --feature <feature-id>`.

Workflow:
- Read `git diff` of changed files.
- Map file paths to feature ids using the existing skill folders.
- Re-read only the affected features' source.
- Re-run Stage 3 only on those features.
- Increment `version`, set `last_updated` to today, commit with message `chore: update <feature> skill (auto)`.

Stage 2 (Plan) only re-runs when a brand-new feature appears (new package, new Struts action, new Quartz job class).

---

## Delivery Surfaces

The agent ships as two equivalent forms that share the same prompt strings:

| Form | Where it runs | Best for |
|---|---|---|
| **Claude skill** (markdown spec) | GitHub Copilot Chat, Claude Code CLI, Claude Cowork | Interactive use, exploring a new repo, one-off runs |
| **Python CLI** (`skill-gen crawl \| plan \| generate \| link \| update`) | Terminal, CI, GitHub Action | Deterministic runs, large repos needing rate limiting and checkpointing, automation |

Both produce identical output. The CLI is what runs in GitHub Actions for Phase 2 PR-merge automation.

---

## Multi-Repo Support

Enterprises have 50–200 Java repos. A central `agent-config.yml` registers them all:

```yaml
repos:
  - name: payment-service
    path: /enterprise/payment-service
  - name: finance-service
    path: /enterprise/finance-service
```

`skill-gen generate-all --config agent-config.yml` runs across the entire portfolio in one pass. Each repo gets its own `.github/skills/` directory and its own checkpoint file.

---

## Hard Constraints

- The agent emits SKILL.md files. It does **not** emit Java code as a primary deliverable.
- The agent must accurately describe whatever stack the target repo actually uses. If the repo is Struts, the skill describes Struts — not Spring Boot.
- Skills must be self-contained: reading one SKILL.md gives full feature context with zero additional file reads required.
- The agent must work for legacy apps containing stored procedures and shell scripts, not just modern Spring Boot.
- First-run cost is acceptable. Steady-state cost (incremental updates) must be tiny — that's where the premium-request savings come from.

---

## What This Is Not (clarifying common misreadings)

- **Not a forward code generator.** "Given a feature name, write Controller + Service + DAO + DDL" is not the job. The agent reads existing code and writes instruction files about it.
- **Not a documentation generator for human readers.** The output is AI-readable instruction. Tables and cited rules are tuned for AI consumption, not human reading flow.
- **Not tied to three specific features.** Sample features like "File Delivery", "Invoice Compare", "Payment Method Determination" are *illustrations* of what one feature could look like in one possible project structure. They are not the agent's deliverable set. The agent ships for whatever features exist in whatever repo a developer points it at.

---

## What I Want From You

Please answer these five questions explicitly, in order. Push back hard if anything is unclear or wrong.

1. **Does this design make sense as described, or is there a hole in the logic?** Where would it break first?
2. **Is the 4-stage Crawl → Plan → Generate → Link pipeline the right shape**, or would a different split work better given the token budget and the incremental-update requirement?
3. **The "no Java code in skill bodies" rule — keep it or relax it?** What's the actual tradeoff? When does each form win?
4. **For legacy apps** with a mix of stored procs + shell scripts + Java + XML wiring, **how should the agent infer feature boundaries** when the package-name signal isn't enough? Is package name even the right primary signal for those apps?
5. **What's the biggest risk** in this design that has not yet been considered? What's the most likely way the first real enterprise repo this is pointed at makes the agent produce bad skills?

Be specific. Cite the part of the brief you're responding to. If you would design the agent differently from the ground up, say so and explain why.
