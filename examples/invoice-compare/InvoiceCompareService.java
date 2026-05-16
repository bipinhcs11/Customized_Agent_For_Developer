package com.company.app.invoicecompare.service;

import com.company.app.invoicecompare.model.dto.*;
import com.company.app.invoicecompare.model.enums.InvoiceComparisonStatus;

import java.util.List;

/**
 * Business service contract for Invoice Compare.
 */
public interface InvoiceCompareService {

    /**
     * Compares two invoices and persists the result with all line-item mismatches.
     *
     * @param request the comparison request (source + target invoice references)
     * @return the comparison result
     */
    InvoiceCompareResponse compare(InvoiceCompareRequest request);

    /**
     * Retrieves a comparison result by ID.
     */
    InvoiceCompareResponse getById(Long id);

    /**
     * Retrieves all line-item mismatches for a given comparison.
     */
    List<InvoiceLineItemMismatchResponse> getMismatches(Long comparisonId);

    /**
     * Approves a COMPLETED comparison.
     */
    InvoiceCompareResponse approve(Long id, String reviewedBy, String notes);

    /**
     * Rejects a COMPLETED comparison.
     */
    InvoiceCompareResponse reject(Long id, String reviewedBy, String notes);

    /**
     * Returns all comparisons, optionally filtered by status.
     */
    List<InvoiceCompareResponse> getByStatus(InvoiceComparisonStatus status);
}
