---
skill: File Delivery
domain: file-delivery
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

# File Delivery

## Purpose
Manages the full lifecycle of files moving through the system — upload, virus scan, storage, secure delivery to a recipient, and acknowledgement. Ensures uploaded files are correctly sized, typed, and scanned before they become deliverable, and tracks who received what and when so the business has a verifiable delivery audit trail.

## Entry Points
- REST: POST   /api/v1/file-delivery/upload                   → FileDeliveryController.upload()
- REST: GET    /api/v1/file-delivery/{id}                     → FileDeliveryController.getById()
- REST: GET    /api/v1/file-delivery/{id}/download            → FileDeliveryController.download()
- REST: GET    /api/v1/file-delivery/status/{id}              → FileDeliveryController.getStatus()
- REST: GET    /api/v1/file-delivery/user/{uploadedBy}        → FileDeliveryController.getByUploader()
- REST: PUT    /api/v1/file-delivery/{id}/acknowledge         → FileDeliveryController.acknowledge()
- REST: DELETE /api/v1/file-delivery/{id}                     → FileDeliveryController.delete()

## Business Logic

### Core Flow
1. Validate file size and MIME type against configured limits — FileDeliveryServiceImpl.upload()
2. Generate a UUID-based storage path and persist the file to local FS or S3 — FileDeliveryServiceImpl.upload()
3. Compute SHA-256 checksum for integrity verification — FileDeliveryServiceImpl.upload()
4. Persist a FileDeliveryEntity with status PENDING — FileDeliveryServiceImpl.upload()
5. Submit an asynchronous virus scan — FileDeliveryServiceImpl.upload()
6. On scan complete, transition status to READY or SCAN_FAILED — FileDeliveryServiceImpl (scan callback)
7. On first successful download, transition status to DELIVERED and stamp deliveredAt — FileDeliveryServiceImpl.download()
8. On acknowledge, transition status to ACKNOWLEDGED — FileDeliveryServiceImpl.acknowledge()
9. On delete, soft-delete by setting status=DELETED and is_active=false; schedule async storage cleanup — FileDeliveryServiceImpl.delete()

### Validation Rules
- File size must not exceed app.file-delivery.max-size-mb (default 100 MB) — FileDeliveryServiceImpl.validateFile()
- MIME type must appear in the configured allowlist app.file-delivery.allowed-types — FileDeliveryServiceImpl.validateFile()
- Download is rejected unless current status is READY (FileDeliveryStatus.isDeliverable() returns true) — FileDeliveryServiceImpl.download()
- Acknowledge is rejected unless current status is DELIVERED — FileDeliveryServiceImpl.acknowledge()
- @Valid on the request body enforces non-blank deliveredTo and required fields — FileDeliveryController.upload()

### Business Rules
- Status lifecycle: PENDING → SCANNING → READY → DELIVERED → ACKNOWLEDGED; terminal branches SCAN_FAILED, EXPIRED, DELETED — FileDeliveryStatus enum
- isDeliverable() returns true only for READY; isTerminal() returns true for SCAN_FAILED, EXPIRED, DELETED — FileDeliveryStatus.isDeliverable() / FileDeliveryStatus.isTerminal()
- Files in READY state expire after app.file-delivery.expiry-days days (default 7) — FileDeliveryServiceImpl (expiry sweep)
- Download count is incremented on every successful download — FileDeliveryServiceImpl.download()
- First download (downloadCount transitions 0→1) triggers DELIVERED transition and stamps deliveredAt — FileDeliveryServiceImpl.download()
- Once DELIVERED or ACKNOWLEDGED, file content cannot be replaced — FileDeliveryServiceImpl.upload() (existing-record guard)
- Delete is soft only: sets status=DELETED and is_active=false; physical storage is cleaned up asynchronously — FileDeliveryServiceImpl.delete()
- Enum stored as VARCHAR(30), never as ordinal — FileDeliveryEntity.status mapping

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| FileDeliveryController.java | Controller | REST entry points for upload, download, status, acknowledge, delete |
| FileDeliveryService.java | Service Interface | Business contract for file delivery operations |
| FileDeliveryServiceImpl.java | Service | Upload validation, storage orchestration, status transitions, download accounting |
| FileDeliveryDao.java | DAO Interface | Data-access contract |
| FileDeliveryDaoImpl.java | Repository | JPA-backed persistence with soft-delete filter and find-by-uploader / find-by-status queries |
| FileDeliveryEntity.java | Entity | Persistent record for a single file delivery |
| FileDeliveryRequest.java | DTO | Inbound payload for upload |
| FileDeliveryResponse.java | DTO | Outbound payload for all read endpoints |
| FileDeliveryStatusResponse.java | DTO | Lightweight status-only response |
| FileDeliveryStatus.java | Enum | Lifecycle states with isDeliverable() and isTerminal() helpers |
| application.yml | Config | app.file-delivery.* keys for size limit, allowed types, expiry, storage path |

## Data Flow
[POST /api/v1/file-delivery/upload (multipart)]
  → FileDeliveryController.upload()
  → FileDeliveryServiceImpl.validateFile()
  → StorageService.store() (local FS or S3)
  → ChecksumService.sha256()
  → FileDeliveryDaoImpl.save() (status=PENDING)
  → ScanService.submitScan() (async)
  → FileDeliveryResponse

## Database & Storage
- Tables: file_delivery (id, file_name, file_type, file_size_bytes, storage_path, checksum, status, uploaded_by, delivered_to, delivered_at, expires_at, download_count, created_at, updated_at, created_by, is_active)
- File paths: configurable via app.file-delivery.storage.base-path (default /var/files/delivery)
- Storage backend: local filesystem or S3, selected by app.file-delivery.storage.type
- Indexes: idx_file_delivery_status, idx_file_delivery_uploaded_by, idx_file_delivery_delivered_to, idx_file_delivery_expires_at (partial WHERE status='READY')
- Constraints: storage_path is UNIQUE; status NOT NULL with default 'PENDING'

## External Dependencies
- StorageService — abstracts file persistence to local filesystem or S3 bucket
- ScanService — submits files to asynchronous virus scanner and receives scan-complete callbacks
- ChecksumService — computes SHA-256 hash of uploaded file content

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| BusinessRuleException | File exceeds size limit, MIME type not in allowlist, or status transition not permitted (e.g., download in non-READY state) | Thrown from FileDeliveryServiceImpl; GlobalExceptionHandler returns HTTP 400 |
| ResourceNotFoundException | findActiveOrThrow() called with unknown id or soft-deleted record | Thrown from FileDeliveryServiceImpl; GlobalExceptionHandler returns HTTP 404 |
| MethodArgumentNotValidException | @Valid binding failure on request body | Caught globally; GlobalExceptionHandler returns HTTP 400 with field errors |

## Edge Cases
- Soft-deleted records (is_active=false) are excluded from all find-by queries — FileDeliveryDaoImpl
- First download transitions status to DELIVERED; subsequent downloads only increment download_count — FileDeliveryServiceImpl.download()
- Files past expiresAt remain in READY status until the expiry sweep runs — FileDeliveryServiceImpl (expiry job)
- Storage cleanup runs asynchronously after soft-delete so the audit record persists immediately — FileDeliveryServiceImpl.delete()
- @Transactional(readOnly=true) on read methods so Hibernate skips dirty checks — FileDeliveryServiceImpl.getById() / FileDeliveryServiceImpl.getByUploader()

## Legacy Notes
none found

## Related Skills
none found

## AI Agent Instructions
1. Never invent status values outside FileDeliveryStatus (PENDING, SCANNING, READY, DELIVERED, ACKNOWLEDGED, SCAN_FAILED, EXPIRED, DELETED) — adding a value requires a DB migration and breaks isDeliverable() / isTerminal() helpers in FileDeliveryStatus
2. Always check the configurable allowlist app.file-delivery.allowed-types before adding a MIME type — never hardcode MIME types in FileDeliveryServiceImpl.validateFile()
3. Never hard-delete a file_delivery row — soft-delete sets status=DELETED and is_active=false; every query depends on the is_active filter in FileDeliveryDaoImpl
4. The endpoint path prefix /api/v1/file-delivery must not change without updating dependent services that consume these endpoints
5. Storage backend selection (local vs S3) is config-driven via app.file-delivery.storage.type — service code must remain backend-agnostic and route through StorageService
6. The first-download status transition (PENDING/READY → DELIVERED) is load-bearing for delivery reporting — do not change FileDeliveryServiceImpl.download() without auditing downstream consumers of deliveredAt
