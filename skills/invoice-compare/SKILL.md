---
skill: Invoice Compare
domain: invoice-compare
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

# Invoice Compare

## Purpose
Compares two invoices originating from different systems (for example an ERP and a vendor portal) at the line-item level, flags discrepancies by type, computes the net amount difference, and routes the result to a human reviewer who can approve or reject the reconciliation. Gives finance teams an auditable record of every mismatch and who signed off on the resolution.

## Entry Points
- REST: POST /api/v1/invoice-compare/compare              → InvoiceCompareController.compare()
- REST: GET  /api/v1/invoice-compare/{id}                 → InvoiceCompareController.getById()
- REST: GET  /api/v1/invoice-compare/{id}/mismatches      → InvoiceCompareController.getMismatches()
- REST: PUT  /api/v1/invoice-compare/{id}/approve         → InvoiceCompareController.approve()
- REST: PUT  /api/v1/invoice-compare/{id}/reject          → InvoiceCompareController.reject()
- REST: GET  /api/v1/invoice-compare/status/{status}      → InvoiceCompareController.getByStatus()

## Business Logic

### Core Flow
1. Persist a new InvoiceComparisonEntity with status PENDING — InvoiceCompareServiceImpl.compare()
2. Fetch source and target invoice data from their respective systems — InvoiceCompareServiceImpl.compare() (via InvoiceFetchService)
3. Transition status to IN_PROGRESS — InvoiceCompareServiceImpl.compare()
4. Index source and target line items by line number into maps for O(1) lookup — InvoiceCompareServiceImpl.compareLineItems()
5. For each source line missing in target, emit MISSING_IN_TARGET — InvoiceCompareServiceImpl.compareLineItems()
6. For each source line present in target, compare amount, quantity, description, and tax; emit one mismatch per differing field — InvoiceCompareServiceImpl.compareLineItems()
7. For each target line not present in source, emit MISSING_IN_SOURCE — InvoiceCompareServiceImpl.compareLineItems()
8. Compute net total difference (target.total − source.total) — InvoiceCompareServiceImpl.computeTotalDiff()
9. Update the comparison header with totalMismatchCount and totalAmountDiff, transition status to COMPLETED — InvoiceCompareServiceImpl.compare()
10. Persist all mismatch rows linked to the comparison id — InvoiceCompareServiceImpl.compare() (via InvoiceLineItemMismatchDao)
11. On approve, set status=APPROVED, stamp reviewedBy and reviewedAt — InvoiceCompareServiceImpl.approve()
12. On reject, set status=REJECTED, store reconciliationNotes, stamp reviewer — InvoiceCompareServiceImpl.reject()

### Validation Rules
- @Valid on the request body enforces non-null sourceInvoiceId, targetInvoiceId, sourceSystem, targetSystem — InvoiceCompareController.compare()
- Approve and reject require reviewedBy as a query parameter — InvoiceCompareController.approve() / InvoiceCompareController.reject()
- Reject requires non-empty notes — InvoiceCompareController.reject()
- Approve/reject are rejected unless current status is COMPLETED or RESUBMITTED (InvoiceComparisonStatus.isReviewable() returns true) — InvoiceCompareServiceImpl.approve() / InvoiceCompareServiceImpl.reject()

### Business Rules
- Status lifecycle: PENDING → IN_PROGRESS → COMPLETED → APPROVED; rejected comparisons branch COMPLETED → REJECTED → RESUBMITTED → COMPLETED — InvoiceComparisonStatus enum
- isReviewable() returns true only for COMPLETED and RESUBMITTED — InvoiceComparisonStatus.isReviewable()
- Mismatch types: AMOUNT_MISMATCH, MISSING_IN_SOURCE, MISSING_IN_TARGET, DESCRIPTION_MISMATCH, QUANTITY_MISMATCH, TAX_MISMATCH — MismatchType enum
- Line items are matched by lineItemNumber, not by description or amount — InvoiceCompareServiceImpl.compareLineItems()
- Net amount diff is signed: positive means target total exceeds source total — InvoiceCompareServiceImpl.computeTotalDiff()
- Each mismatch row records both source and target values plus the numeric diffAmount where applicable — InvoiceCompareServiceImpl.buildMismatch()
- Resolved flag on a mismatch row is independent of the parent comparison status — InvoiceLineItemMismatchEntity.resolved
- Enums stored as VARCHAR, never ordinal — InvoiceComparisonEntity.comparisonStatus / InvoiceLineItemMismatchEntity.mismatchType

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| InvoiceCompareController.java | Controller | REST entry points for compare, get, mismatches, approve, reject, getByStatus |
| InvoiceCompareService.java | Service Interface | Business contract for invoice comparison operations |
| InvoiceCompareServiceImpl.java | Service | Comparison algorithm, mismatch generation, review workflow |
| InvoiceCompareDao.java | DAO Interface | Header-record data-access contract |
| InvoiceCompareDaoImpl.java | Repository | JPA-backed persistence for InvoiceComparisonEntity |
| InvoiceLineItemMismatchDao.java | DAO Interface | Mismatch-row data-access contract |
| InvoiceLineItemMismatchDaoImpl.java | Repository | JPA-backed persistence for mismatch rows |
| InvoiceComparisonEntity.java | Entity | Header record for one comparison run |
| InvoiceLineItemMismatchEntity.java | Entity | Child record for a single line-item mismatch |
| InvoiceCompareRequest.java | DTO | Inbound payload for /compare |
| InvoiceCompareResponse.java | DTO | Outbound payload for header reads |
| InvoiceLineItemMismatchResponse.java | DTO | Outbound payload for /mismatches |
| InvoiceComparisonStatus.java | Enum | Header status lifecycle with isReviewable() helper |
| MismatchType.java | Enum | Type of mismatch at the line-item level |

## Data Flow
[POST /api/v1/invoice-compare/compare]
  → InvoiceCompareController.compare()
  → InvoiceCompareServiceImpl.compare()
  → InvoiceFetchService.fetch() x2 (source + target)
  → InvoiceCompareServiceImpl.compareLineItems()
  → InvoiceCompareServiceImpl.computeTotalDiff()
  → InvoiceCompareDaoImpl.save() (status=COMPLETED)
  → InvoiceLineItemMismatchDaoImpl.saveAll()
  → InvoiceCompareResponse

## Database & Storage
- Tables: invoice_comparison (id, source_invoice_id, target_invoice_id, source_system, target_system, comparison_status, total_mismatch_count, total_amount_diff, reconciliation_notes, reviewed_by, reviewed_at, created_at, updated_at, created_by, is_active)
- Tables: invoice_line_item_mismatch (id, comparison_id FK, line_item_number, mismatch_type, field_name, source_value, target_value, diff_amount, resolved, created_at)
- Indexes: idx_invoice_comparison_status, idx_invoice_comparison_source, idx_invoice_comparison_target, idx_invoice_mismatch_comparison, idx_invoice_mismatch_type
- Constraints: invoice_line_item_mismatch.comparison_id REFERENCES invoice_comparison(id); comparison_status NOT NULL with default 'PENDING'
- File paths: none found
- Queues: none found

## External Dependencies
- InvoiceFetchService — retrieves invoice header and line items from upstream systems (ERP, vendor portal, SAP, etc.); the sourceSystem and targetSystem strings select the backend adapter

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| ResourceNotFoundException | findById() called with unknown comparison id during getById / approve / reject | Thrown from InvoiceCompareServiceImpl; GlobalExceptionHandler returns HTTP 404 |
| BusinessRuleException | Approve or reject attempted when status is not isReviewable() | Thrown from InvoiceCompareServiceImpl; GlobalExceptionHandler returns HTTP 400 |
| MethodArgumentNotValidException | @Valid binding failure on InvoiceCompareRequest | Caught globally; GlobalExceptionHandler returns HTTP 400 with field errors |

## Edge Cases
- A line number present in both source and target with identical values produces zero mismatch rows — InvoiceCompareServiceImpl.compareLineItems()
- A line present in both but differing in multiple fields produces one mismatch row per differing field — InvoiceCompareServiceImpl.compareLineItems()
- A comparison with zero mismatches still completes successfully with totalMismatchCount=0 — InvoiceCompareServiceImpl.compare()
- Rejected comparisons may be resubmitted, returning to COMPLETED via RESUBMITTED — InvoiceComparisonStatus.RESUBMITTED
- diffAmount is nullable for non-numeric mismatch types (DESCRIPTION_MISMATCH) — InvoiceLineItemMismatchEntity.diffAmount

## Legacy Notes
none found

## Related Skills
none found

## AI Agent Instructions
1. Never invent mismatch types outside MismatchType (AMOUNT_MISMATCH, MISSING_IN_SOURCE, MISSING_IN_TARGET, DESCRIPTION_MISMATCH, QUANTITY_MISMATCH, TAX_MISMATCH) — these are persisted as strings and consumed by reviewer dashboards
2. Never match line items by description or amount — line_item_number is the only matching key in InvoiceCompareServiceImpl.compareLineItems()
3. Approve and reject must check InvoiceComparisonStatus.isReviewable() — do not bypass this guard in InvoiceCompareServiceImpl.approve() / InvoiceCompareServiceImpl.reject()
4. Total amount diff is signed (target − source); flipping the sign breaks downstream reconciliation reports — preserve in InvoiceCompareServiceImpl.computeTotalDiff()
5. Mismatch rows have a FK to invoice_comparison(id); never delete a comparison without first handling its child mismatches — and prefer soft-delete via is_active
6. The InvoiceFetchService adapter is selected by sourceSystem / targetSystem strings — new system names require both an adapter and an update to this skill
