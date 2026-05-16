# Layered Architecture Reference

## Layer Responsibilities

### Controller
- Entry point for all HTTP requests.
- Responsible for: input validation (`@Valid`), HTTP status codes, request/response mapping.
- Must NOT contain business logic.
- Must NOT call DAO directly.
- Inject Service (interface, not impl) via constructor.

### Service (Interface)
- Defines the business contract — what the system can do.
- Keep method signatures clean: accept DTOs or primitives, return DTOs.
- Do not expose entity objects outside the service layer.

### ServiceImpl
- Owns all business logic, orchestration, and rule enforcement.
- Annotate class with `@Transactional`; read-only methods get `@Transactional(readOnly = true)`.
- Maps between DTOs ↔ entities (use private helper methods or a dedicated mapper class).
- Throws domain-specific exceptions (`ResourceNotFoundException`, `BusinessRuleException`).
- Inject DAO (interface) via constructor.

### DAO (Interface)
- Defines the data-access contract — how data is stored and retrieved.
- Method names should be semantically clear: `findByStatus`, `countByUser`, etc.
- No SQL / JPQL in the interface.

### DaoImpl
- Implements data access using JPA Repository or JDBC Template.
- **JPA Repository**: for standard CRUD and simple queries. Create a `{Feature}JpaRepository extends JpaRepository<{Feature}Entity, Long>` inner interface.
- **JDBC Template**: for complex queries, bulk operations, or when JPA N+1 is a concern.
- Annotate with `@Repository`.
- Map `ResultSet` → Entity manually when using JDBC.

### DB Schema
- One primary table per feature entity.
- Always include audit columns: `created_at`, `updated_at`, `created_by`, `is_active`.
- Use `BIGSERIAL` (Postgres) or `BIGINT AUTO_INCREMENT` (MySQL) for primary keys.
- Index columns used in WHERE clauses of common queries.

---

## JPA vs JDBC Template Decision Guide

| Situation | Use |
|---|---|
| Standard CRUD | JPA Repository |
| Simple filter by 1-2 columns | JPA Repository (derived query) |
| Complex multi-table JOIN | JDBC Template |
| Bulk insert/update | JDBC Template (`batchUpdate`) |
| Stored procedure call | JDBC Template |
| Aggregation (SUM, COUNT with GROUP BY) | JDBC Template |
| Pagination of simple queries | JPA Repository (`Pageable`) |

---

## Transaction Boundaries

- Transactions start at the Service layer, never the Controller or DAO.
- A single Service method = a single transaction.
- If a Service method calls multiple DAO methods, they all participate in the same transaction — this is the point.
- Mark read-only queries with `@Transactional(readOnly = true)` — Hibernate skips dirty checks and the DB can use read replicas.

---

## Exception Handling Strategy

Define custom exceptions in a shared `exception` package:

```java
// 404 - resource not found
public class ResourceNotFoundException extends RuntimeException { ... }

// 400 - business rule violated
public class BusinessRuleException extends RuntimeException { ... }

// 409 - duplicate / conflict
public class DuplicateResourceException extends RuntimeException { ... }
```

Handle globally with `@ControllerAdvice` — do not catch and re-throw in the service layer unless you need to add context.

---

## Entity Design

```java
@Entity
@Table(name = "{feature_snake}")
public class {Feature}Entity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // feature-specific fields

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @Column(name = "created_by")
    private String createdBy;

    @Column(name = "is_active", nullable = false)
    private boolean isActive = true;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }
}
```
