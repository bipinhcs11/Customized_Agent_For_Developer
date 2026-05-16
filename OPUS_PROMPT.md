# FeatureBased Skill Generator Agent — Full Context Prompt for Claude Opus

> **Historical document.** This is the original problem statement that bootstrapped the project. The first implementation assumed direct Anthropic API calls; the current implementation (v0.3+) is **host-agent-driven** — every LLM-dependent stage emits a prompt file and ingests a saved response, so no API key or outbound network call is required. The pipeline shape, four-stage decomposition, and SKILL.md standard described below are unchanged.

---

## Who You Are

You are a senior software architect and AI agent designer. You are helping build a
**FeatureBased Skill Generator Agent** — a system that reads Java/Spring Boot codebases,
understands them feature by feature, and writes structured `SKILL.md` files that serve as
**living, AI-readable documentation**. These skill files are then consumed by GitHub Copilot
and Claude to give them accurate, up-to-date context about any feature — without needing to
re-read the entire codebase on every request.

---

## The Core Problem Being Solved

In enterprise Java development:
- Repos are large. Features span many files across Controller → Service → DAO → DB.
- GitHub Copilot and Claude have limited context windows. Without the right context loaded,
  they give generic, inaccurate answers.
- Developers waste time repeating context to the AI: "this is the FileDelivery feature,
  it does X, the DB table is Y, the status enum is Z..."
- When code changes, the AI has no way of knowing — it continues giving stale answers.
- In large enterprises there can be 50–200 Java repos. Keeping AI context accurate across
  all of them manually is impossible.

---

## The Solution: FeatureBased Skill Generator Agent

A purpose-built agent that does two things:

### Phase 1 — Skill Generation
1. Scans a Java/Spring Boot repo
2. Identifies each business feature (by Controller name, package, or config)
3. Reads all layers for that feature:
   - `{Feature}Controller.java` → REST endpoints, request/response types, validations
   - `{Feature}Service.java` / `{Feature}ServiceImpl.java` → business rules, orchestration
   - `{Feature}Dao.java` / `{Feature}DaoImpl.java` → queries, data-access patterns
   - DB migration files / schema SQL → table structure, indexes, constraints
4. Writes a comprehensive `SKILL.md` file per feature inside a `skills/` folder in the repo
5. The SKILL.md captures ALL context an AI needs: endpoints, payloads, business logic,
   status enums, DB schema, config keys, edge cases, error handling

### Phase 2 — Skill Maintenance
1. Watches for code changes (PR merge, file save, git commit hook, or GitHub Action)
2. Detects which feature was changed (by file path → feature mapping)
3. Re-reads only the changed feature's code
4. Updates the relevant `SKILL.md` to reflect the new code
5. Commits the updated skill back to the repo

---

## How GitHub Copilot Uses the Skills

Once skill files exist in the repo, Copilot reads them as context via:
- `.github/copilot-instructions.md` — tells Copilot where skills live and how to use them
- Copilot's workspace indexing picks up `skills/**/*.md` automatically
- When a developer asks "how does invoice comparison work?" or "add a new status to file delivery",
  Copilot reads the relevant SKILL.md and gives an accurate, contextual answer — without
  needing to scan hundreds of Java files

The result:
- **Fewer premium Copilot requests** (skills pre-package context, so shorter conversations)
- **Better answers** (skills are accurate and always up-to-date)
- **No back-and-forth** (developer gets right answer first time)
- **Faster onboarding** (new devs ask Copilot questions, Copilot reads skills)

---

## Three Reference Features

The agent was designed around three real enterprise features as reference implementations:

### 1. File Delivery
**What it does**: Manages the full lifecycle of files moving through a system — upload,
virus scan, storage, delivery to a recipient, acknowledgement.

**Layer stack**:
- Controller: `/api/v1/file-delivery` — upload (multipart), download, getStatus, acknowledge, delete
- Service: upload validates file size + MIME type, stores to disk/S3, computes SHA-256 checksum,
  triggers async virus scan, transitions status
- DAO: JPA-backed, soft-delete pattern, find-by-uploader and find-by-status queries
- Status lifecycle: `PENDING → SCANNING → READY → DELIVERED → ACKNOWLEDGED | SCAN_FAILED | EXPIRED | DELETED`
- DB table: `file_delivery` with columns: file_name, file_type, file_size_bytes, storage_path,
  checksum, status, uploaded_by, delivered_to, delivered_at, expires_at, download_count

**Key config**:
```yaml
app.file-delivery.max-size-mb: 100
app.file-delivery.allowed-types: [application/pdf, text/csv, image/jpeg]
app.file-delivery.expiry-days: 7
app.file-delivery.storage.base-path: /var/files/delivery
```

**Business rules**:
- Files > 100 MB rejected
- Status transitions are strict (can't download unless READY, can't acknowledge unless DELIVERED)
- Download increments download_count, first download triggers DELIVERED transition
- Soft delete: sets status = DELETED + is_active = false

---

### 2. Invoice Compare
**What it does**: Compares two invoices (from different systems — ERP vs vendor portal) at the
line-item level, flags discrepancies by type, computes total amount diff, and routes result to
a human reviewer who approves or rejects.

**Layer stack**:
- Controller: `/api/v1/invoice-compare` — compare (POST), getById, getMismatches, approve, reject, listByStatus
- Service: fetches invoice data from source + target systems, runs line-item comparison algorithm,
  persists comparison header + mismatch child records, manages review workflow
- DAO: two JPA repositories — InvoiceComparisonEntity + InvoiceLineItemMismatchEntity
- Status lifecycle: `PENDING → IN_PROGRESS → COMPLETED → APPROVED | REJECTED`
- DB tables:
  - `invoice_comparison`: source/target invoice IDs, systems, status, total_mismatch_count,
    total_amount_diff, reviewed_by, reviewed_at
  - `invoice_line_item_mismatch`: comparison_id (FK), line_item_number, mismatch_type,
    field_name, source_value, target_value, diff_amount, resolved

**Mismatch types**: `AMOUNT_MISMATCH`, `MISSING_IN_SOURCE`, `MISSING_IN_TARGET`,
  `DESCRIPTION_MISMATCH`, `QUANTITY_MISMATCH`, `TAX_MISMATCH`

**Comparison algorithm**:
1. Index source lines by line number → Map<Integer, LineItem>
2. Index target lines by line number → Map<Integer, LineItem>
3. For each source line: if missing in target → MISSING_IN_TARGET; else compare amount, qty, desc
4. For each target line not in source: → MISSING_IN_SOURCE
5. Net amount diff = target.total - source.total

---

### 3. Payment Method Determination
**What it does**: Evaluates a transaction's context (amount, currency, customer type, country,
merchant category) against a configurable priority-ordered rule set and determines which payment
method to use. Supports manual overrides with full audit trail.

**Layer stack**:
- Controller: `/api/v1/payment-method-determination` — determine (POST), getById,
  getByTransactionId, override, getHistory (paginated), listRules, createRule, updateRule, setRuleActive
- Service: loads all active rules ordered by priority, evaluates each rule in order (first-match wins),
  falls back to configured default if no rule matches, override flow sets OVERRIDDEN status + audit fields
- DAO: two JPA repositories — PaymentMethodDeterminationEntity + PaymentRuleEntity
- Status: `DETERMINED`, `OVERRIDDEN`, `NO_RULE_MATCH`, `FAILED`
- Payment methods: `CREDIT_CARD`, `DEBIT_CARD`, `BANK_TRANSFER`, `WIRE_TRANSFER`, `ACH`, `SEPA`, etc.
- DB tables:
  - `payment_method_determination`: transaction_id (UNIQUE), amount, currency, customer_type,
    country, merchant_category, determined_method, rule_applied, determination_status,
    override_reason, overridden_by, overridden_at
  - `payment_rule`: rule_name (UNIQUE), priority, customer_type, min_amount, max_amount,
    currency, country, merchant_category, determined_method, is_active

**Rule engine logic** (first-match, priority ascending):
```
if rule.customer_type != null && rule.customer_type != req.customer_type → skip
if rule.currency != null && rule.currency != req.currency → skip
if rule.country != null && rule.country != req.country → skip
if rule.min_amount != null && req.amount < rule.min_amount → skip
if rule.max_amount != null && req.amount > rule.max_amount → skip
→ MATCH: use rule.determined_method
```

**Seed rules** (examples):
```sql
('Government large USD wire',  priority=5,  customer_type=GOVERNMENT, min=10000, currency=USD → WIRE_TRANSFER)
('Corporate high-value wire',  priority=10, customer_type=CORPORATE,   min=50000, currency=USD → WIRE_TRANSFER)
('EU individual SEPA',         priority=20, customer_type=INDIVIDUAL,  currency=EUR            → SEPA)
('Default credit card',        priority=99, all-null                                           → CREDIT_CARD)
```

---

## Architecture & Conventions Used

**Stack**: Spring Boot 3.x, Java 17+, Spring Data JPA, JDBC Template, PostgreSQL, Maven, SLF4J

**Naming conventions** (strictly enforced):
| Layer | Pattern | Example |
|---|---|---|
| Controller | `{Feature}Controller` | `FileDeliveryController` |
| Service interface | `{Feature}Service` | `FileDeliveryService` |
| Service impl | `{Feature}ServiceImpl` | `FileDeliveryServiceImpl` |
| DAO interface | `{Feature}Dao` | `FileDeliveryDao` |
| DAO impl | `{Feature}DaoImpl` | `FileDeliveryDaoImpl` |
| Entity | `{Feature}Entity` | `FileDeliveryEntity` |
| Request DTO | `{Feature}Request` | `FileDeliveryRequest` |
| Response DTO | `{Feature}Response` | `FileDeliveryResponse` |
| DB table | `{feature_snake}` | `file_delivery` |

**Package structure**:
```
com.company.{module}.{featureLower}
├── controller/
├── service/
├── service/impl/
├── dao/
├── dao/impl/
└── model/
    ├── entity/
    ├── dto/
    └── enums/
```

**Code rules**:
- Constructor injection everywhere (never `@Autowired` fields)
- `@Transactional` on ServiceImpl class; `@Transactional(readOnly=true)` on read methods
- `ResponseEntity<T>` on all controller methods
- `@Valid` on all request body parameters
- Soft delete (`is_active = false`) — never hard DELETE
- Every table has: `id BIGSERIAL PK`, `created_at`, `updated_at`, `created_by`, `is_active`
- Enums stored as `VARCHAR` (never ordinal)
- DAO impl embeds its JpaRepository as a private inner interface
- Global `@ControllerAdvice` handles all exceptions (never catch-and-rethrow in service)

---

## Repository Structure (GitHub)

**Repo**: `https://github.com/bipinhcs11/Customized_Agent_For_Developer.git`

```
Customized_Agent_For_Developer/
├── AGENT.md                              ← Agent specification
├── CLAUDE.md                             ← Claude/Cowork config
├── README.md
├── .github/
│   └── copilot-instructions.md           ← Copilot custom instructions
├── skills/
│   ├── feature-skill-generator/          ← Core agent skill
│   │   ├── SKILL.md
│   │   ├── references/
│   │   │   ├── architecture.md
│   │   │   └── patterns.md
│   │   └── templates/
│   │       ├── Controller.java.tmpl
│   │       ├── Service.java.tmpl
│   │       ├── ServiceImpl.java.tmpl
│   │       ├── Dao.java.tmpl
│   │       ├── DaoImpl.java.tmpl
│   │       └── schema.sql.tmpl
│   ├── file-delivery/SKILL.md
│   ├── invoice-compare/SKILL.md
│   └── payment-method-determination/SKILL.md
└── examples/
    ├── file-delivery/                    ← 6 Java files + SQL
    ├── invoice-compare/                  ← 6 Java files + SQL
    └── payment-method-determination/     ← 6 Java files + SQL
```

---

## What Is Still Missing / Needs to Be Built

The following was discussed and identified as the **correct next phase** but not yet built:

### 1. Skill Generator Agent (reads code → writes skills)
The agent needs to:
- Accept a target Java repo path as input
- Auto-detect feature boundaries (by scanning Controller class names, packages)
- For each detected feature, read all Java files in that feature's layers
- Extract and summarize:
  - All REST endpoints (method, path, request body, response type)
  - All business rules in ServiceImpl
  - All DAO queries (JPQL, native SQL, derived query method names)
  - DB table DDL + column meanings
  - Status enums and their transitions
  - Config keys used (`@Value`)
  - Exception types thrown
- Write a structured `SKILL.md` in `{target-repo}/skills/{feature}/SKILL.md`
- The SKILL.md must be rich enough that an AI reading ONLY that file has complete
  understanding of the feature — no need to open any Java file

### 2. Skill Updater Agent (detects code change → updates skill)
Triggered by:
- GitHub Action on PR merge (preferred for enterprise)
- Git pre-commit hook (lightweight, local)
- File watcher (for real-time local dev)
- Manual CLI command: `agent update-skill --feature FileDelivery`

The updater:
- Receives a list of changed Java files (from git diff)
- Maps file paths → feature names (e.g., `FileDeliveryServiceImpl.java` → `file-delivery`)
- Re-reads only the changed feature's code
- Diffs the new understanding against the existing SKILL.md
- Updates only the changed sections
- Commits the updated skill file with message: `chore: update file-delivery skill (auto)`

### 3. GitHub Copilot Integration
- `.github/copilot-instructions.md` should tell Copilot:
  - "Read `skills/{feature}/SKILL.md` before answering any question about a feature"
  - "After making code changes to any feature, trigger skill update"
  - "When a developer asks about a feature by name, load the corresponding skill"
- Copilot should never generate code that contradicts the skill (e.g., wrong status enum value,
  wrong endpoint path, wrong DTO field name)

### 4. Enterprise Multi-Repo Support
- A central config file (`agent-config.yml`) lists all repos:
  ```yaml
  repos:
    - name: payment-service
      path: /enterprise/payment-service
      features:
        - FileDelivery
        - PaymentMethodDetermination
    - name: finance-service
      path: /enterprise/finance-service
      features:
        - InvoiceCompare
  ```
- The agent can run across all repos in one pass: `agent generate-all --config agent-config.yml`
- Each repo gets its own `skills/` directory

---

## Three Claude Artifact Links (Need to Be Read)

These three public Claude artifacts contain the original detailed specification for this agent.
They were shared by the user but could not be fetched during the session due to tool restrictions.
**Read these first before doing anything else:**

1. https://claude.ai/public/artifacts/89b22944-5134-4295-8836-938432f48b06
2. https://claude.ai/public/artifacts/3467e791-5cf1-44bc-be5d-05119a2018c8
3. https://claude.ai/public/artifacts/1689b220-c09f-467c-a8af-1eb3bb1a30fe

These likely contain the exact SKILL.md format, the agent prompt template, and/or the
GitHub Copilot integration specification. The entire repo structure should be aligned to whatever
those artifacts define.

---

## Key Design Principles (User's Words)

> "The main goal is to save GitHub Copilot premium requests, get better results because skills
> are updated and accurate, increase productivity, no back and forth."

> "In enterprise there will be so many repos. First goal: it generates the feature-based skills.
> Then maintain it."

> "After any code update happens, make sure the agent updates these skills based on new code
> changes as well."

> "Skills are updated and accurate — the model will have all the context from the skill files
> when asking any question, doing analysis, or debugging."

---

## What Your Task Is

1. **Read the three artifact links above** — understand the exact original specification
2. **Reconcile** what was built so far (in the GitHub repo) against the original spec
3. **Identify gaps** — what's missing, what's wrong, what needs to change
4. **Redesign or extend** the repository so it correctly implements:
   - The skill generator (reads Java code → writes SKILL.md)
   - The skill updater (detects code changes → updates SKILL.md)
   - The Copilot integration (tells Copilot how to use skill files)
   - The enterprise multi-repo config
5. **Produce the corrected files** and explain what changed from the initial version and why

---

## Constraints

- Do NOT use Lombok unless explicitly asked
- Do NOT generate Spring Security unless asked
- Do NOT skip the DB schema — always include it
- Spring Boot 3.x, Java 17+
- PostgreSQL as default database
- Constructor injection everywhere
- The agent itself should be usable from GitHub Copilot Chat, Claude Cowork, and Claude Code CLI
- Skills must be self-contained — reading one SKILL.md gives full feature context with zero
  additional file reads required
