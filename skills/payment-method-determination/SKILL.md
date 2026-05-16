---
skill: Payment Method Determination
domain: payment-method-determination
version: 1
project_type: REST API
framework: Spring Boot
java_version: 17
legacy: false
status: active
flags: none
related_skills: none
generated_by: human
last_updated: 2026-05-15
---

# Payment Method Determination

## Purpose
Evaluates a transaction's context (amount, currency, customer type, country, merchant category) against a configurable priority-ordered rule set and determines which payment method the system should use. Supports manual overrides with a full audit trail, so finance and operations teams can adapt routing without code changes and trace every override back to the person who made it.

## Entry Points
- REST: POST /api/v1/payment-method-determination/determine               → PaymentMethodDeterminationController.determine()
- REST: GET  /api/v1/payment-method-determination/{id}                    → PaymentMethodDeterminationController.getById()
- REST: GET  /api/v1/payment-method-determination/transaction/{txId}      → PaymentMethodDeterminationController.getByTransactionId()
- REST: PUT  /api/v1/payment-method-determination/{id}/override           → PaymentMethodDeterminationController.override()
- REST: GET  /api/v1/payment-method-determination/history                 → PaymentMethodDeterminationController.getHistory()
- REST: GET  /api/v1/payment-method-determination/rules                   → PaymentMethodDeterminationController.listRules()
- REST: POST /api/v1/payment-method-determination/rules                   → PaymentMethodDeterminationController.createRule()
- REST: PUT  /api/v1/payment-method-determination/rules/{ruleId}          → PaymentMethodDeterminationController.updateRule()

## Business Logic

### Core Flow
1. Load all active payment rules ordered by priority ascending (lower priority value evaluated first) — PaymentMethodDeterminationServiceImpl.determine()
2. Evaluate rules in order; the first rule whose predicates all match wins (first-match-wins) — PaymentMethodDeterminationServiceImpl.determine()
3. Build a PaymentMethodDeterminationEntity capturing the input context (transactionId, amount, currency, customerType, merchantCategory, country) — PaymentMethodDeterminationServiceImpl.determine()
4. If a rule matched: set determinedMethod, ruleApplied=rule.ruleName, status=DETERMINED — PaymentMethodDeterminationServiceImpl.determine()
5. If no rule matched: set determinedMethod=null, ruleApplied=null, status=NO_RULE_MATCH; log warning — PaymentMethodDeterminationServiceImpl.determine()
6. Persist the determination entity — PaymentMethodDeterminationServiceImpl.determine()
7. On override: replace determinedMethod with the override value, capture overrideReason / overriddenBy / overriddenAt, transition status to OVERRIDDEN — PaymentMethodDeterminationServiceImpl.override()
8. Rule CRUD endpoints maintain the payment_rule table independently of the determination flow — PaymentMethodDeterminationServiceImpl.listRules() / createRule() / updateRule()

### Validation Rules
- @Valid on the request body enforces required transactionId, amount, currency, customerType — PaymentMethodDeterminationController.determine()
- transaction_id has a UNIQUE constraint at the database level; duplicate inserts fail with DuplicateResourceException — PaymentMethodDeterminationServiceImpl.determine()
- Override requests must include a non-null paymentMethod, reason, and overriddenBy — PaymentMethodDeterminationController.override()
- Rule creation requires a unique ruleName (UNIQUE constraint on payment_rule.rule_name) — PaymentMethodDeterminationServiceImpl.createRule()
- Rule priority must be set (NOT NULL constraint) — PaymentRuleEntity.priority

### Business Rules
- Payment methods: CREDIT_CARD, DEBIT_CARD, BANK_TRANSFER, WIRE_TRANSFER, ACH, SEPA, PAYPAL, CRYPTO, INVOICE_CREDIT, CASH_ON_DELIVERY — PaymentMethodType enum
- Customer types: INDIVIDUAL, CORPORATE, GOVERNMENT, NON_PROFIT — CustomerType enum
- Determination status values: DETERMINED, OVERRIDDEN, NO_RULE_MATCH, FAILED — DeterminationStatus enum
- isFinal() returns true only for DETERMINED and OVERRIDDEN — DeterminationStatus.isFinal()
- Rule match predicates are conjunctive: a null predicate matches anything; a non-null predicate must match the request value to keep the rule in contention — PaymentMethodDeterminationServiceImpl.matchesRule()
- Numeric predicate semantics: req.amount < rule.minAmount fails; req.amount > rule.maxAmount fails — PaymentMethodDeterminationServiceImpl.matchesRule()
- Currency and country comparisons are case-insensitive — PaymentMethodDeterminationServiceImpl.matchesRule()
- Priority ordering: lower integer wins; a Default rule with all-null predicates and priority=99 acts as the catch-all — payment_rule seed data
- Cached rules refresh every app.payment-method-determination.cache-ttl-seconds seconds (default 300) — PaymentMethodDeterminationServiceImpl (rule cache)
- Overrides are permanent: once status=OVERRIDDEN, re-running determine() for the same transaction is a no-op — PaymentMethodDeterminationServiceImpl.override()
- Enums stored as VARCHAR, never ordinal — PaymentMethodDeterminationEntity / PaymentRuleEntity mappings

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| PaymentMethodDeterminationController.java | Controller | REST entry points for determine, get, override, history, and rule CRUD |
| PaymentMethodDeterminationService.java | Service Interface | Business contract for determination and rule management |
| PaymentMethodDeterminationServiceImpl.java | Service | Rule loading, first-match-wins evaluation, override workflow, rule CRUD |
| PaymentMethodDeterminationDao.java | DAO Interface | Determination-record data-access contract |
| PaymentMethodDeterminationDaoImpl.java | Repository | JPA-backed persistence for PaymentMethodDeterminationEntity |
| PaymentRuleDao.java | DAO Interface | Rule data-access contract |
| PaymentRuleDaoImpl.java | Repository | JPA-backed persistence with findAllActiveOrderByPriority() |
| PaymentMethodDeterminationEntity.java | Entity | One row per determination request, with override fields |
| PaymentRuleEntity.java | Entity | One row per configured rule |
| PaymentMethodDeterminationRequest.java | DTO | Inbound payload for /determine |
| PaymentMethodDeterminationResponse.java | DTO | Outbound payload for determine and read endpoints |
| PaymentMethodOverrideRequest.java | DTO | Inbound payload for /override |
| PaymentRuleRequest.java | DTO | Inbound payload for rule create/update |
| PaymentRuleResponse.java | DTO | Outbound payload for rule reads |
| PaymentMethodType.java | Enum | The set of payment methods a rule may select |
| CustomerType.java | Enum | The customer-type predicates a rule may match |
| DeterminationStatus.java | Enum | Determination outcome lifecycle with isFinal() helper |
| application.yml | Config | app.payment-method-determination.* keys for caching, default fallback, override toggle |

## Data Flow
[POST /api/v1/payment-method-determination/determine]
  → PaymentMethodDeterminationController.determine()
  → PaymentMethodDeterminationServiceImpl.determine()
  → PaymentRuleDaoImpl.findAllActiveOrderByPriority() (cached)
  → PaymentMethodDeterminationServiceImpl.matchesRule() (per rule, first match wins)
  → PaymentMethodDeterminationDaoImpl.save() (status=DETERMINED or NO_RULE_MATCH)
  → PaymentMethodDeterminationResponse

## Database & Storage
- Tables: payment_method_determination (id, transaction_id UNIQUE, amount, currency, customer_type, merchant_category, country, determined_method, rule_applied, determination_status, override_reason, overridden_by, overridden_at, created_at, updated_at, created_by, is_active)
- Tables: payment_rule (id, rule_name UNIQUE, priority NOT NULL, customer_type, min_amount, max_amount, currency, country, merchant_category, determined_method NOT NULL, is_active, created_at, updated_at, created_by)
- Indexes: idx_pmd_transaction_id, idx_pmd_status, idx_pmd_customer_type, idx_payment_rule_priority (partial WHERE is_active=TRUE)
- Seed rules: Corporate high-value wire (priority=10), EU individual SEPA (priority=20), Default credit card (priority=99)
- Cache keys: in-memory rule cache, TTL configurable via app.payment-method-determination.cache-ttl-seconds (default 300s)
- File paths: none found
- Queues: none found

## External Dependencies
- none found

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| ResourceNotFoundException | findById() called with unknown determination id during getById or override | Thrown from PaymentMethodDeterminationServiceImpl; GlobalExceptionHandler returns HTTP 404 |
| DuplicateResourceException | Inserting a determination with a transaction_id that already exists | Thrown from PaymentMethodDeterminationServiceImpl; GlobalExceptionHandler returns HTTP 409 |
| BusinessRuleException | Attempting to override when app.payment-method-determination.enable-override=false | Thrown from PaymentMethodDeterminationServiceImpl.override(); GlobalExceptionHandler returns HTTP 400 |
| MethodArgumentNotValidException | @Valid binding failure on request body | Caught globally; GlobalExceptionHandler returns HTTP 400 with field errors |

## Edge Cases
- A NO_RULE_MATCH determination still persists with status=NO_RULE_MATCH; the warning log is the only operator signal — PaymentMethodDeterminationServiceImpl.determine()
- Rule cache may serve stale rules for up to cache-ttl-seconds after a rule update — PaymentMethodDeterminationServiceImpl (rule cache)
- A rule with all-null predicates matches every request; the seed catch-all "Default credit card" at priority=99 relies on this — PaymentMethodDeterminationServiceImpl.matchesRule()
- Priority ties are resolved by database insertion order (no secondary sort key) — PaymentRuleDaoImpl.findAllActiveOrderByPriority()
- Override after status=DETERMINED is allowed; override after status=OVERRIDDEN replaces the previous override and updates overriddenAt — PaymentMethodDeterminationServiceImpl.override()
- Currency and country comparisons use equalsIgnoreCase, so "usd" matches "USD" — PaymentMethodDeterminationServiceImpl.matchesRule()

## Legacy Notes
none found

## Related Skills
none found

## AI Agent Instructions
1. Never change the first-match-wins semantics — rule priority is the ONLY tiebreaker. Reordering matchesRule() to score-best-match will break existing rule sets in PaymentMethodDeterminationServiceImpl.determine()
2. Never invent payment method values outside PaymentMethodType — these are persisted as strings and consumed by downstream payment processors that switch on the exact string
3. Null predicates on a rule mean "match anything" — preserve this in PaymentMethodDeterminationServiceImpl.matchesRule() (do NOT treat null as "require absent")
4. transaction_id is UNIQUE — re-running determine() for the same txId must be a guarded no-op, not a duplicate insert
5. Overrides are first-class business events: never silently mutate determinedMethod without setting status=OVERRIDDEN and stamping overriddenBy / overriddenAt in PaymentMethodDeterminationServiceImpl.override()
6. The rule cache TTL is configurable; never bypass the cache on the hot path of determine() — only invalidate it after rule writes in createRule() / updateRule()
7. When adding a new CustomerType or PaymentMethodType, add a migration plus an update to this skill — downstream rule authoring UIs read these enums
