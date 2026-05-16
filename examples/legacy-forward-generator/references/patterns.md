# Coding Patterns & Conventions

## DTO Mapping

### Option A — Manual mapping helpers (default, no extra dependencies)

Place private methods in ServiceImpl:

```java
private FileDeliveryEntity mapToEntity(FileDeliveryRequest req) {
    FileDeliveryEntity entity = new FileDeliveryEntity();
    entity.setFileName(req.getFileName());
    entity.setFileType(req.getFileType());
    entity.setStatus(FileDeliveryStatus.PENDING);
    entity.setUploadedBy(req.getUploadedBy());
    return entity;
}

private FileDeliveryResponse mapToResponse(FileDeliveryEntity entity) {
    FileDeliveryResponse response = new FileDeliveryResponse();
    response.setId(entity.getId());
    response.setFileName(entity.getFileName());
    response.setStatus(entity.getStatus().name());
    response.setCreatedAt(entity.getCreatedAt());
    return response;
}
```

### Option B — MapStruct (if user requests it)

```java
@Mapper(componentModel = "spring")
public interface FileDeliveryMapper {
    FileDeliveryEntity toEntity(FileDeliveryRequest request);
    FileDeliveryResponse toResponse(FileDeliveryEntity entity);
}
```

Only suggest MapStruct if the feature has many fields (>10) or the user explicitly asks.

---

## Request DTO Pattern

```java
public class {Feature}Request {

    @NotBlank(message = "{fieldName} is required")
    private String fieldName;

    @NotNull(message = "amount is required")
    @Positive(message = "amount must be positive")
    private BigDecimal amount;

    // getters and setters
}
```

Always use Jakarta Bean Validation annotations (`jakarta.validation.constraints.*`).
Use `@NotBlank` for Strings, `@NotNull` for objects/primitives, `@Positive`/`@Min`/`@Max` for numbers.

---

## Response DTO Pattern

```java
public class {Feature}Response {
    private Long id;
    private String status;
    private LocalDateTime createdAt;
    // all fields the caller needs (not the entity's raw DB columns)
    // getters and setters
}
```

Never expose the entity class directly to the controller. Always map to a response DTO.

---

## Enum Pattern

```java
public enum {Feature}Status {
    PENDING,
    IN_PROGRESS,
    COMPLETED,
    FAILED,
    CANCELLED;

    public boolean isTerminal() {
        return this == COMPLETED || this == FAILED || this == CANCELLED;
    }
}
```

Store enums as strings in the DB:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false, length = 30)
private {Feature}Status status;
```

---

## Error Response DTO

```java
public class ErrorResponse {
    private String message;
    private String code;
    private LocalDateTime timestamp;
    private List<FieldError> fieldErrors; // for validation errors

    // constructors, getters
}
```

---

## GlobalExceptionHandler

```java
@ControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleNotFound(ResourceNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                             .body(new ErrorResponse(ex.getMessage(), "NOT_FOUND"));
    }

    @ExceptionHandler(BusinessRuleException.class)
    public ResponseEntity<ErrorResponse> handleBusinessRule(BusinessRuleException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                             .body(new ErrorResponse(ex.getMessage(), "BUSINESS_RULE_VIOLATION"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException ex) {
        List<FieldError> fieldErrors = ex.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(e -> new FieldError(e.getField(), e.getDefaultMessage()))
            .toList();
        ErrorResponse response = new ErrorResponse("Validation failed", "VALIDATION_ERROR");
        response.setFieldErrors(fieldErrors);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(response);
    }
}
```

---

## JDBC Template RowMapper

```java
private static final RowMapper<{Feature}Entity> ROW_MAPPER = (rs, rowNum) -> {
    {Feature}Entity entity = new {Feature}Entity();
    entity.setId(rs.getLong("id"));
    entity.setStatus({Feature}Status.valueOf(rs.getString("status")));
    entity.setCreatedAt(rs.getTimestamp("created_at").toLocalDateTime());
    entity.setIsActive(rs.getBoolean("is_active"));
    return entity;
};
```

---

## Logging Convention

Use SLF4J with a static logger:

```java
private static final Logger log = LoggerFactory.getLogger({Feature}ServiceImpl.class);

// Info for normal flow
log.info("Creating {} with name: {}", "{Feature}", request.getName());

// Warn for recoverable anomalies
log.warn("{} with id {} not found, returning empty", "{Feature}", id);

// Error for exceptions (include exception as last arg for stack trace)
log.error("Failed to process {}: {}", "{Feature}", ex.getMessage(), ex);
```

---

## Pagination (when needed)

Controller:
```java
@GetMapping
public ResponseEntity<Page<{Feature}Response>> getAll(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    Pageable pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
    return ResponseEntity.ok(service.getAll(pageable));
}
```

Service method signature:
```java
Page<{Feature}Response> getAll(Pageable pageable);
```
