"""
Single source of truth for every prompt the agent sends to Claude.

These prompts are the load-bearing part of the agent. Both the Python CLI and
the Claude skill (skills/skill-generator/SKILL.md) reference them, so changes
here ripple to both delivery surfaces.

Each prompt comes directly from the artifact-2 pipeline spec at
https://claude.ai/public/artifacts/3467e791-5cf1-44bc-be5d-05119a2018c8
with light edits for clarity. The artifact-3 SKILL.md schema referenced inside
the Stage 3 prompt lives at
https://claude.ai/public/artifacts/1689b220-c09f-467c-a8af-1eb3bb1a30fe
"""
from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Plan
# ─────────────────────────────────────────────────────────────────────────────

STAGE_2_PLAN_PROMPT = """You are a Java codebase analyst. Group the classes, XML signals, SQL signals, and shell-script signals below into business domains.

Rules for grouping:
- Primary signal: package name
- Secondary signal: class name prefix (FileDelivery*, SeedData*, Search*)
- Tertiary signal: annotations, XML mappings, SQL stored-procedure callers
- Each domain: 5–25 classes typically
- God classes (flagged god_class): split by method name cohesion groups — treat each group as its own domain entry with isGodClassSplit: true
- Deprecated classes: include, flag in output
- Generated classes: exclude
- Shared utilities used by 3+ domains: assign to domain id "shared-infrastructure"
- Spring/Hibernate XML beans: assign to the same domain as the Java class they reference
- Struts actions: assign to domain of the Service they call
- Batch Jobs/Steps: one domain per distinct Job if business logic differs
- Stored procedures (.sql): assign to the domain that calls them (look at SQL invocations in shell scripts and DAO classes)
- Shell scripts (.sh): assign to the batch domain they orchestrate
- Default package: group by longest common class name prefix

Respond ONLY with this JSON, no markdown, no explanation:
{
  "projectType": "Microservice|Monolith|Batch|Hybrid|Legacy",
  "framework": "Spring Boot|Struts|Spring MVC|Quarkus|Spring Batch|Raw Servlet|Unknown",
  "buildSystem": "Maven|Gradle|Ant|Unknown",
  "javaVersion": "8|11|17|21|Unknown",
  "warnings": [],
  "domains": [
    {
      "id": "kebab-case-id",
      "name": "Human Readable Name",
      "description": "One sentence business description",
      "classes": ["ClassName", "ClassName.methodGroup*"],
      "xmlSources": ["filename.xml: signal description"],
      "sqlSources": ["filename.sql: stored proc / table description"],
      "shellSources": ["filename.sh: orchestrates Java job"],
      "configKeys": ["datasource.*"],
      "confidence": "HIGH|MEDIUM|LOW",
      "isGodClassSplit": false,
      "godClassParent": null,
      "flags": ["deprecated"],
      "estimatedTokens": 0
    }
  ]
}

The crawl index follows. Use it as your only source of truth — do not invent classes or signals not present in the index.

INDEX:
{INDEX_JSON}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — Generate
# ─────────────────────────────────────────────────────────────────────────────

STAGE_3_GENERATE_PROMPT = """Generate a SKILL.md for an AI coding agent (GitHub Copilot or Claude) to understand and work on this Java feature.

Output ONLY raw markdown. No preamble. No code fences around the whole response. No explanation.

Use EXACTLY this structure. Every section is required — write the literal string "none found" where a section has no content. Never omit a section, never reorder.

---
skill: [Title Case feature name, max 5 words]
domain: {DOMAIN_ID}
version: 1
project_type: [REST API | Batch Job | Scheduled | Hybrid | Monolith Module | Stored-Procedure Driven]
framework: [Spring Boot | Struts | Spring MVC | Quarkus | Spring Batch | Raw Servlet | Unknown]
java_version: [8 | 11 | 17 | 21 | Unknown]
legacy: [true | false]
status: [active | deprecated | migrating]
flags: [comma-separated: deprecated, god_class_split, xml_driven, batch, shared, no_tests, partial, or "none"]
related_skills: PLACEHOLDER
generated_by: skill_generator.agent
last_updated: {TODAY}
---

# [Feature Name]

## Purpose
[2–3 sentences. Business value only. No class names. No tech stack terms. Answer: what business problem does this solve?]

## Entry Points
[Every way the feature can be triggered. Cite the exact handler class and method.]
- REST:    METHOD /path → ClassName.methodName()
- Struts:  /path.do → ActionClass.execute()
- Job:     JobName → StepName → ProcessorClass.process()
- Cron:    @Scheduled("0 0 * * *") → ClassName.methodName()
- Event:   @KafkaListener(topic) → ClassName.methodName()
- Shell:   script.sh → ClassName.main()

## Business Logic

### Core Flow
[Numbered steps. Each step = one sentence. Cite the class responsible at the end of each line.]
1. [Step] — ClassName.methodName()
2. [Step] — ClassName.methodName()

### Validation Rules
[Every validation found in the code. Cite class.method for each.]
- [Rule] — ClassName.methodName()

### Business Rules
[Domain rules inferred from method logic. Cite source.]
- [Rule] — ClassName.methodName()

## Key Classes & Files
[Every file that belongs to this domain.]
| File | Type | Role |
|------|------|------|
| ClassName.java | Controller / Action / Job / Service / Repository / DTO / Validator / Config / Enum / Exception | One-line role |
| filename.xml | Spring XML / Struts Config / Hibernate Mapping / web.xml | One-line role |
| script.sh | Shell | One-line role |
| migration.sql | SQL Migration / Stored Procedure / DDL | One-line role |

## Data Flow
[Tree-style ASCII showing method nesting, async/sync semantics, DB destinations, and inline behavioral notes. This section must be RICH — it is the highest-signal part of the skill for an AI generating code. Mimic the pattern below exactly.]

Required structural elements (use the ones the source supports):
- Top: entry trigger line (HTTP method + path, `@KafkaListener(topic)`, `@Scheduled(...)`, batch Job name, or shell-script invocation)
- Vertical chain with `|` and `v` for sequential flow at the top level
- Tree branches with `|--` (or `+--` / `└──`) where one method fans out into multiple
- Method calls shown with their argument flow inline: `param -> intermediate -> finalCall()`
- DB / external-system destinations at the leaves: `-> Primary DB`, `-> Kafka topic.x`, `-> S3 bucket`, `-> External API`
- Annotation context inline where it changes execution: `@Async("taskExecutor")`, `@Transactional(readOnly=true)`, `@Retryable`
- Behavioral notes after a left-arrow describing runtime behavior: `<- iterates SSN list`, `<- blocks; effectively sequential fan-out`, `<- set-difference query pair`, `<- summary metric`, `<- cached for 5 min`
- Output construction at the bottom: `Build 5-tab XSSFWorkbook -> return InputStreamResource`
- Side effects on `+` lines: `+ write copy to filesystem`, `+ emit OrderCreated event`, `+ audit log row`

Template shape (replace placeholder names with the real ones from the source):

```
GET /api/comparison/v1/all
   |
   v
ControllerName.endpoint()
   |   resolve dependencies via JobExecutionService
   v
WriterClass.writeToXlsx()
   |
   |-- resolveListMethod()
   |       inputParam -> intermediate -> getFinalValue()
   |
   |-- processItems()           <- iterates input list
   |       for each item:
   |          AsyncComponent.callAsync()    @Async("taskExecutor")
   |             |__ ValidatorClass.validate()
   |                    |- getPrimaryDetails()      -> Primary DB
   |                    |- getSecondaryDetails()    -> Secondary DB
   |                    |- compareDetails(primaryWins=true)
   |                    |- compareDetails(primaryWins=false)
   |          .get()                              <- blocks; effectively sequential fan-out
   |
   |-- getMissingInPrimary()                       <- set-difference query pair
   |-- getMissingInSecondary()                     <- set-difference query pair
   |-- getOptimizedSubset()                        <- summary metric
   |
   |-- Build 5-tab XSSFWorkbook -> return InputStreamResource
            + write copy to filesystem
```

Reuse vertical bars and the same depth of indentation per level. Keep the diagram aligned. Only describe what the source actually does — never invent a branch.

## Database & Storage
[Every persistence concern.]
- Tables:        [table names from Hibernate mappings, SQL strings, or DDL files]
- Stored procs:  [procedure names if called from this domain]
- File paths:    [from properties files or hardcoded strings]
- Queues:        [topic or queue names]
- Cache keys:    [if caching found]

## External Dependencies
[Everything this domain calls outside its own classes.]
- [Service name or class] — [what it does for this domain]
- [HTTP endpoint or client] — [purpose]
- [SMTP / file system / message broker / stored procedure] — [purpose]

## Error Handling
[Every exception type found.]
| Exception | Trigger | Handling |
|-----------|---------|---------|
| ExceptionClass | What causes it | How it is caught or propagated |

## Edge Cases
[Defensive code found in the source. Cite class.method.]
- [Null check / boundary / fallback] — ClassName.methodName()

## Legacy Notes
[Populate only if legacy: true or status: deprecated/migrating.]
- [Deprecated markers, @SuppressWarnings, TODO/FIXME comments]
- [Migration hints if @Deprecated found]
- [Tech debt that must not be made worse]

## Related Skills
[Cross-domain dependencies. Will be populated by the link pass.]
| Domain | Relationship | Reason |
|--------|-------------|--------|
| [domain-id] | calls / shares / extends / configures | [exact reason citing class and method] |

## AI Agent Instructions
[Precise rules for any AI agent working on this feature. These are constraints, not suggestions. Be specific.]
1. [What to always check before changing business logic — cite the class]
2. [What must never be broken — cite the method]
3. [Which related skill will be affected by changes here — be specific]
4. [How to run tests for this domain — command or class name]
5. [Any constraint specific to this domain's legacy or architecture]

---

Hard rules for your output:
- Only describe what is actually in the source below. Never invent business rules.
- When logic is ambiguous, annotate: "inferred from ClassName.methodName()".
- Cite ClassName.methodName() for every rule and entry point. No floating claims.
- Do NOT paste Java code in the body. Tables and prose only.
- Use the literal "none found" for any section with no applicable content.
- The Purpose section must contain zero class names and zero tech-stack terms.

DOMAIN: {DOMAIN_ID}
DOMAIN NAME: {DOMAIN_NAME}
DOMAIN DESCRIPTION: {DOMAIN_DESCRIPTION}

SOURCE FILES:

{SOURCE_BLOB}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4 — Link
# ─────────────────────────────────────────────────────────────────────────────

STAGE_4_LINK_PROMPT = """Find cross-domain dependencies between these Java feature skills.

Signals to look for:
- Direct class instantiation across domains
- Injected services from another domain
- Shared DAOs / repositories
- Exceptions thrown in one domain caught in another
- Config values shared across domains
- Stored procedures called from one domain that another domain also references
- Shell scripts in one domain that invoke Java classes in another

Respond ONLY with this JSON, no markdown, no explanation:
{
  "links": [
    {
      "from": "domain-id",
      "to": "domain-id",
      "reason": "exact reason citing class and method",
      "type": "calls|shares|extends|configures"
    }
  ]
}

SKILL SUMMARIES:

{SUMMARIES}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — Update prompt (Stage 3 with an additional diff context)
# ─────────────────────────────────────────────────────────────────────────────

PHASE_2_UPDATE_PROMPT_PREFIX = """The following Java feature has had code changes. The existing SKILL.md is provided below the source. Re-generate the SKILL.md so it accurately reflects the new source. Increment `version` by 1 from the existing value, and set `last_updated` to today's date ({TODAY}). Preserve `related_skills` from the existing skill unless the changes obviously affect cross-domain relationships.

All other rules from the Generate stage apply unchanged.

EXISTING SKILL.MD:

{EXISTING_SKILL_MD}

---

NEW SOURCE FILES:

{SOURCE_BLOB}
"""
