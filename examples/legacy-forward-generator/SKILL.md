---
name: feature-skill-generator
description: >
  Use this skill whenever the user asks to generate, scaffold, or create a Java/Spring Boot feature
  following the Controller → Service → DAO → DAO Impl → DB Schema layered architecture.
  Trigger on phrases like: "generate feature", "create full stack", "scaffold new feature",
  "create Controller Service DAO", "new Spring Boot feature", or any mention of creating
  FileDelivery, InvoiceCompare, or PaymentMethodDetermination code.
  Always use this skill when the user describes a business feature and wants Java code generated
  for it — even if they only mention one layer (generate all layers unless explicitly told otherwise).
---

# Feature Skill Generator

This skill produces a complete, production-ready Java/Spring Boot feature implementation across all layers of the standard architecture used in this project.

## Layer Stack (always generate all of these)

```
Controller  →  Service (interface)  →  ServiceImpl  →  Dao (interface)  →  DaoImpl  →  DB Schema
```

Never skip a layer. If a layer has no meaningful logic for the feature, generate a proper stub with a comment explaining it.

---

## Step-by-Step Generation Process

### Step 1 — Understand the Feature

Extract from the user's request:
- **Feature name** (derive PascalCase: e.g., "file delivery" → `FileDelivery`)
- **Core entity fields** (what data does this feature manage?)
- **Operations / use cases** (what actions does the system need to perform?)
- **Business rules** (any constraints, validations, or logic?)
- **Package root** (ask if not provided; default to `com.company.app.{feature_lower}`)

If the user's request is ambiguous, ask one focused clarifying question before generating.

### Step 2 — Generate in Order

Generate each layer in this sequence, top to bottom:

1. **Model classes** — Entity, Request DTO, Response DTO, any Enums
2. **Controller** — REST endpoints
3. **Service interface** — business contract
4. **ServiceImpl** — business logic
5. **DAO interface** — data-access contract
6. **DaoImpl** — JPA / JDBC implementation
7. **DB Schema** — DDL SQL

### Step 3 — Verify Completeness

Before finishing, confirm:
- [ ] All CRUD operations present (or explained if intentionally omitted)
- [ ] Constructor injection used (no field `@Autowired`)
- [ ] `ResponseEntity<T>` used in all controller methods
- [ ] `@Transactional` on ServiceImpl class
- [ ] `@Valid` on controller request bodies
- [ ] DB schema has `id`, `created_at`, `updated_at`, `is_active`
- [ ] Javadoc on all public methods

---

## Naming Reference

| Layer | Pattern | Example (feature = FileDelivery) |
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

---

## Package Structure

```
com.company.{module}.{feature_lower}
├── controller/       {Feature}Controller.java
├── service/          {Feature}Service.java
├── service/impl/     {Feature}ServiceImpl.java
├── dao/              {Feature}Dao.java
├── dao/impl/         {Feature}DaoImpl.java
└── model/
    ├── entity/       {Feature}Entity.java
    ├── dto/          {Feature}Request.java
    │                 {Feature}Response.java
    └── enums/        {Feature}Status.java (if needed)
```

---

## Code Patterns

### Controller

```java
@RestController
@RequestMapping("/api/v1/{feature-kebab}")
@Validated
public class {Feature}Controller {

    private final {Feature}Service service;

    public {Feature}Controller({Feature}Service service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<{Feature}Response> create(
            @Valid @RequestBody {Feature}Request request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.create(request));
    }

    @GetMapping("/{id}")
    public ResponseEntity<{Feature}Response> getById(@PathVariable Long id) {
        return ResponseEntity.ok(service.getById(id));
    }

    @GetMapping
    public ResponseEntity<List<{Feature}Response>> getAll() {
        return ResponseEntity.ok(service.getAll());
    }

    @PutMapping("/{id}")
    public ResponseEntity<{Feature}Response> update(
            @PathVariable Long id,
            @Valid @RequestBody {Feature}Request request) {
        return ResponseEntity.ok(service.update(id, request));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
```

### Service Interface

```java
public interface {Feature}Service {
    {Feature}Response create({Feature}Request request);
    {Feature}Response getById(Long id);
    List<{Feature}Response> getAll();
    {Feature}Response update(Long id, {Feature}Request request);
    void delete(Long id);
}
```

### ServiceImpl

```java
@Service
@Transactional
public class {Feature}ServiceImpl implements {Feature}Service {

    private final {Feature}Dao dao;

    public {Feature}ServiceImpl({Feature}Dao dao) {
        this.dao = dao;
    }

    @Override
    public {Feature}Response create({Feature}Request request) {
        {Feature}Entity entity = mapToEntity(request);
        entity = dao.save(entity);
        return mapToResponse(entity);
    }

    @Override
    @Transactional(readOnly = true)
    public {Feature}Response getById(Long id) {
        return dao.findById(id)
                  .map(this::mapToResponse)
                  .orElseThrow(() -> new ResourceNotFoundException(
                      "{Feature} not found with id: " + id));
    }

    // mapping helpers
    private {Feature}Entity mapToEntity({Feature}Request req) { ... }
    private {Feature}Response mapToResponse({Feature}Entity entity) { ... }
}
```

### DAO Interface

```java
public interface {Feature}Dao {
    {Feature}Entity save({Feature}Entity entity);
    Optional<{Feature}Entity> findById(Long id);
    List<{Feature}Entity> findAll();
    void deleteById(Long id);
    boolean existsById(Long id);
}
```

### DaoImpl (JPA)

```java
@Repository
public class {Feature}DaoImpl implements {Feature}Dao {

    private final {Feature}JpaRepository jpaRepository;

    public {Feature}DaoImpl({Feature}JpaRepository jpaRepository) {
        this.jpaRepository = jpaRepository;
    }

    @Override public {Feature}Entity save({Feature}Entity entity) {
        return jpaRepository.save(entity);
    }
    @Override public Optional<{Feature}Entity> findById(Long id) {
        return jpaRepository.findById(id);
    }
    @Override public List<{Feature}Entity> findAll() {
        return jpaRepository.findAll();
    }
    @Override public void deleteById(Long id) {
        jpaRepository.deleteById(id);
    }
    @Override public boolean existsById(Long id) {
        return jpaRepository.existsById(id);
    }
}
```

### DB Schema

```sql
CREATE TABLE IF NOT EXISTS {feature_snake} (
    id           BIGSERIAL PRIMARY KEY,
    -- feature columns here --
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by   VARCHAR(100),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_{feature_snake}_created_at ON {feature_snake}(created_at);
```

---

## Reference Files

- Read `references/architecture.md` for deeper guidance on layer responsibilities and when to use JDBC vs JPA.
- Read `references/patterns.md` for DTO mapping patterns, exception handling, and transaction boundaries.
- Refer to `templates/` for copy-paste starting points for each layer.

---

## Feature-Specific Skills

For pre-built domain knowledge on supported features, read the corresponding skill:

- **File Delivery** → `../file-delivery/SKILL.md`
- **Invoice Compare** → `../invoice-compare/SKILL.md`
- **Payment Method Determination** → `../payment-method-determination/SKILL.md`

These skills extend this one with feature-specific entity fields, business rules, and status enums — always read the domain skill if the user's request is for one of these features.
