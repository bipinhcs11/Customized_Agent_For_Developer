package com.company.app.invoicecompare.service.impl;

import com.company.app.invoicecompare.dao.InvoiceCompareDao;
import com.company.app.invoicecompare.model.dto.*;
import com.company.app.invoicecompare.model.entity.InvoiceComparisonEntity;
import com.company.app.invoicecompare.model.entity.InvoiceLineItemMismatchEntity;
import com.company.app.invoicecompare.model.enums.InvoiceComparisonStatus;
import com.company.app.invoicecompare.model.enums.MismatchType;
import com.company.app.invoicecompare.service.InvoiceCompareService;
import com.company.app.exception.BusinessRuleException;
import com.company.app.exception.ResourceNotFoundException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Implementation of {@link InvoiceCompareService}.
 * Orchestrates invoice fetching, line-item comparison, and review workflow.
 */
@Service
@Transactional
public class InvoiceCompareServiceImpl implements InvoiceCompareService {

    private static final Logger log = LoggerFactory.getLogger(InvoiceCompareServiceImpl.class);

    private final InvoiceCompareDao dao;

    public InvoiceCompareServiceImpl(InvoiceCompareDao dao) {
        this.dao = dao;
    }

    @Override
    public InvoiceCompareResponse compare(InvoiceCompareRequest request) {
        log.info("Starting invoice comparison: source={} target={}",
                 request.getSourceInvoiceId(), request.getTargetInvoiceId());

        // 1. Create pending comparison header
        InvoiceComparisonEntity comparison = new InvoiceComparisonEntity();
        comparison.setSourceInvoiceId(request.getSourceInvoiceId());
        comparison.setTargetInvoiceId(request.getTargetInvoiceId());
        comparison.setSourceSystem(request.getSourceSystem());
        comparison.setTargetSystem(request.getTargetSystem());
        comparison.setComparisonStatus(InvoiceComparisonStatus.PENDING);
        comparison.setActive(true);
        comparison = dao.save(comparison);

        try {
            // 2. Fetch invoice data from respective systems
            // In a real implementation, call external services or repositories
            InvoiceData source = fetchInvoiceData(request.getSourceInvoiceId(), request.getSourceSystem());
            InvoiceData target = fetchInvoiceData(request.getTargetInvoiceId(), request.getTargetSystem());

            // 3. Mark IN_PROGRESS
            comparison.setComparisonStatus(InvoiceComparisonStatus.IN_PROGRESS);
            dao.save(comparison);

            // 4. Compare line items
            List<InvoiceLineItemMismatchEntity> mismatches = compareLineItems(comparison.getId(), source, target);

            // 5. Compute total amount difference
            BigDecimal totalDiff = target.getTotalAmount().subtract(source.getTotalAmount());

            // 6. Finalize comparison header
            comparison.setTotalMismatchCount(mismatches.size());
            comparison.setTotalAmountDiff(totalDiff);
            comparison.setComparisonStatus(InvoiceComparisonStatus.COMPLETED);
            comparison = dao.save(comparison);

            // 7. Persist mismatches
            dao.saveMismatches(mismatches);

            log.info("Invoice comparison completed: id={}, mismatches={}, amountDiff={}",
                     comparison.getId(), mismatches.size(), totalDiff);

        } catch (Exception e) {
            log.error("Invoice comparison failed: {}", e.getMessage(), e);
            // Leave in PENDING/IN_PROGRESS — a scheduled job can retry
        }

        return mapToResponse(comparison);
    }

    @Override
    @Transactional(readOnly = true)
    public InvoiceCompareResponse getById(Long id) {
        return dao.findById(id)
                  .map(this::mapToResponse)
                  .orElseThrow(() -> new ResourceNotFoundException(
                      "Invoice comparison not found with id: " + id));
    }

    @Override
    @Transactional(readOnly = true)
    public List<InvoiceLineItemMismatchResponse> getMismatches(Long comparisonId) {
        return dao.findMismatchesByComparisonId(comparisonId)
                  .stream()
                  .map(this::mapMismatchToResponse)
                  .collect(Collectors.toList());
    }

    @Override
    public InvoiceCompareResponse approve(Long id, String reviewedBy, String notes) {
        InvoiceComparisonEntity entity = getReviewableEntity(id);
        entity.setComparisonStatus(InvoiceComparisonStatus.APPROVED);
        entity.setReviewedBy(reviewedBy);
        entity.setReconciledNotes(notes);
        entity.setReviewedAt(LocalDateTime.now());
        entity = dao.save(entity);
        log.info("Invoice comparison approved: id={} by={}", id, reviewedBy);
        return mapToResponse(entity);
    }

    @Override
    public InvoiceCompareResponse reject(Long id, String reviewedBy, String notes) {
        InvoiceComparisonEntity entity = getReviewableEntity(id);
        entity.setComparisonStatus(InvoiceComparisonStatus.REJECTED);
        entity.setReviewedBy(reviewedBy);
        entity.setReconciledNotes(notes);
        entity.setReviewedAt(LocalDateTime.now());
        entity = dao.save(entity);
        log.info("Invoice comparison rejected: id={} by={}", id, reviewedBy);
        return mapToResponse(entity);
    }

    @Override
    @Transactional(readOnly = true)
    public List<InvoiceCompareResponse> getByStatus(InvoiceComparisonStatus status) {
        List<InvoiceComparisonEntity> entities = (status != null)
            ? dao.findByStatus(status)
            : dao.findAll();
        return entities.stream().map(this::mapToResponse).collect(Collectors.toList());
    }

    // -------------------------------------------------------------------------
    // Private helpers
    // -------------------------------------------------------------------------

    private InvoiceComparisonEntity getReviewableEntity(Long id) {
        InvoiceComparisonEntity entity = dao.findById(id)
            .orElseThrow(() -> new ResourceNotFoundException(
                "Invoice comparison not found with id: " + id));
        if (!entity.getComparisonStatus().isReviewable()) {
            throw new BusinessRuleException(
                "Comparison is not in a reviewable state: " + entity.getComparisonStatus());
        }
        return entity;
    }

    private InvoiceData fetchInvoiceData(String invoiceId, String system) {
        // TODO: integrate with actual invoice source (ERP, vendor API, etc.)
        // Stub for illustration:
        InvoiceData data = new InvoiceData();
        data.setInvoiceId(invoiceId);
        data.setSystem(system);
        data.setTotalAmount(BigDecimal.ZERO);
        data.setLineItems(Collections.emptyList());
        return data;
    }

    private List<InvoiceLineItemMismatchEntity> compareLineItems(
            Long comparisonId, InvoiceData source, InvoiceData target) {

        List<InvoiceLineItemMismatchEntity> mismatches = new ArrayList<>();
        Map<Integer, LineItem> sourceMap = indexByLine(source.getLineItems());
        Map<Integer, LineItem> targetMap = indexByLine(target.getLineItems());

        // Compare matching lines
        for (Map.Entry<Integer, LineItem> entry : sourceMap.entrySet()) {
            LineItem src = entry.getValue();
            LineItem tgt = targetMap.get(entry.getKey());
            if (tgt == null) {
                mismatches.add(buildMismatch(comparisonId, entry.getKey(),
                    MismatchType.MISSING_IN_TARGET, "amount",
                    src.getAmount().toString(), null, null));
            } else {
                if (src.getAmount().compareTo(tgt.getAmount()) != 0) {
                    mismatches.add(buildMismatch(comparisonId, entry.getKey(),
                        MismatchType.AMOUNT_MISMATCH, "amount",
                        src.getAmount().toString(), tgt.getAmount().toString(),
                        tgt.getAmount().subtract(src.getAmount())));
                }
            }
        }

        // Lines only in target
        for (Integer lineNum : targetMap.keySet()) {
            if (!sourceMap.containsKey(lineNum)) {
                mismatches.add(buildMismatch(comparisonId, lineNum,
                    MismatchType.MISSING_IN_SOURCE, "amount",
                    null, targetMap.get(lineNum).getAmount().toString(), null));
            }
        }

        return mismatches;
    }

    private Map<Integer, LineItem> indexByLine(List<LineItem> items) {
        if (items == null) return Collections.emptyMap();
        Map<Integer, LineItem> map = new LinkedHashMap<>();
        for (LineItem item : items) {
            map.put(item.getLineNumber(), item);
        }
        return map;
    }

    private InvoiceLineItemMismatchEntity buildMismatch(
            Long comparisonId, int lineNum, MismatchType type,
            String fieldName, String srcVal, String tgtVal, BigDecimal diff) {
        InvoiceLineItemMismatchEntity m = new InvoiceLineItemMismatchEntity();
        m.setComparisonId(comparisonId);
        m.setLineItemNumber(lineNum);
        m.setMismatchType(type);
        m.setFieldName(fieldName);
        m.setSourceValue(srcVal);
        m.setTargetValue(tgtVal);
        m.setDiffAmount(diff);
        m.setResolved(false);
        return m;
    }

    private InvoiceCompareResponse mapToResponse(InvoiceComparisonEntity entity) {
        InvoiceCompareResponse r = new InvoiceCompareResponse();
        r.setId(entity.getId());
        r.setSourceInvoiceId(entity.getSourceInvoiceId());
        r.setTargetInvoiceId(entity.getTargetInvoiceId());
        r.setSourceSystem(entity.getSourceSystem());
        r.setTargetSystem(entity.getTargetSystem());
        r.setComparisonStatus(entity.getComparisonStatus().name());
        r.setTotalMismatchCount(entity.getTotalMismatchCount());
        r.setTotalAmountDiff(entity.getTotalAmountDiff());
        r.setReviewedBy(entity.getReviewedBy());
        r.setReviewedAt(entity.getReviewedAt());
        r.setCreatedAt(entity.getCreatedAt());
        return r;
    }

    private InvoiceLineItemMismatchResponse mapMismatchToResponse(
            InvoiceLineItemMismatchEntity entity) {
        InvoiceLineItemMismatchResponse r = new InvoiceLineItemMismatchResponse();
        r.setId(entity.getId());
        r.setLineItemNumber(entity.getLineItemNumber());
        r.setMismatchType(entity.getMismatchType().name());
        r.setFieldName(entity.getFieldName());
        r.setSourceValue(entity.getSourceValue());
        r.setTargetValue(entity.getTargetValue());
        r.setDiffAmount(entity.getDiffAmount());
        r.setResolved(entity.isResolved());
        return r;
    }

    // -------------------------------------------------------------------------
    // Inner data transfer classes (replace with proper DTOs in production)
    // -------------------------------------------------------------------------

    static class InvoiceData {
        private String invoiceId;
        private String system;
        private BigDecimal totalAmount;
        private List<LineItem> lineItems;

        public String getInvoiceId() { return invoiceId; }
        public void setInvoiceId(String invoiceId) { this.invoiceId = invoiceId; }
        public String getSystem() { return system; }
        public void setSystem(String system) { this.system = system; }
        public BigDecimal getTotalAmount() { return totalAmount; }
        public void setTotalAmount(BigDecimal totalAmount) { this.totalAmount = totalAmount; }
        public List<LineItem> getLineItems() { return lineItems; }
        public void setLineItems(List<LineItem> lineItems) { this.lineItems = lineItems; }
    }

    static class LineItem {
        private int lineNumber;
        private BigDecimal amount;
        private String description;

        public int getLineNumber() { return lineNumber; }
        public void setLineNumber(int lineNumber) { this.lineNumber = lineNumber; }
        public BigDecimal getAmount() { return amount; }
        public void setAmount(BigDecimal amount) { this.amount = amount; }
        public String getDescription() { return description; }
        public void setDescription(String description) { this.description = description; }
    }
}
