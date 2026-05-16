package com.company.app.invoicecompare.dao;

import com.company.app.invoicecompare.model.entity.InvoiceComparisonEntity;
import com.company.app.invoicecompare.model.entity.InvoiceLineItemMismatchEntity;
import com.company.app.invoicecompare.model.enums.InvoiceComparisonStatus;

import java.util.List;
import java.util.Optional;

/**
 * Data-access contract for Invoice Compare.
 */
public interface InvoiceCompareDao {

    InvoiceComparisonEntity save(InvoiceComparisonEntity entity);

    Optional<InvoiceComparisonEntity> findById(Long id);

    List<InvoiceComparisonEntity> findAll();

    List<InvoiceComparisonEntity> findByStatus(InvoiceComparisonStatus status);

    void saveMismatches(List<InvoiceLineItemMismatchEntity> mismatches);

    List<InvoiceLineItemMismatchEntity> findMismatchesByComparisonId(Long comparisonId);
}
