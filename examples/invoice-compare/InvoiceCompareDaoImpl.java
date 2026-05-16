package com.company.app.invoicecompare.dao.impl;

import com.company.app.invoicecompare.dao.InvoiceCompareDao;
import com.company.app.invoicecompare.model.entity.InvoiceComparisonEntity;
import com.company.app.invoicecompare.model.entity.InvoiceLineItemMismatchEntity;
import com.company.app.invoicecompare.model.enums.InvoiceComparisonStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

/**
 * JPA-backed implementation of {@link InvoiceCompareDao}.
 */
@Repository
public class InvoiceCompareDaoImpl implements InvoiceCompareDao {

    private final InvoiceComparisonJpaRepository comparisonRepo;
    private final InvoiceLineItemMismatchJpaRepository mismatchRepo;

    public InvoiceCompareDaoImpl(
            InvoiceComparisonJpaRepository comparisonRepo,
            InvoiceLineItemMismatchJpaRepository mismatchRepo) {
        this.comparisonRepo = comparisonRepo;
        this.mismatchRepo = mismatchRepo;
    }

    @Override
    public InvoiceComparisonEntity save(InvoiceComparisonEntity entity) {
        return comparisonRepo.save(entity);
    }

    @Override
    public Optional<InvoiceComparisonEntity> findById(Long id) {
        return comparisonRepo.findByIdAndIsActiveTrue(id);
    }

    @Override
    public List<InvoiceComparisonEntity> findAll() {
        return comparisonRepo.findAllByIsActiveTrue();
    }

    @Override
    public List<InvoiceComparisonEntity> findByStatus(InvoiceComparisonStatus status) {
        return comparisonRepo.findByComparisonStatusAndIsActiveTrue(status);
    }

    @Override
    public void saveMismatches(List<InvoiceLineItemMismatchEntity> mismatches) {
        mismatchRepo.saveAll(mismatches);
    }

    @Override
    public List<InvoiceLineItemMismatchEntity> findMismatchesByComparisonId(Long comparisonId) {
        return mismatchRepo.findByComparisonIdOrderByLineItemNumberAsc(comparisonId);
    }

    interface InvoiceComparisonJpaRepository extends JpaRepository<InvoiceComparisonEntity, Long> {
        Optional<InvoiceComparisonEntity> findByIdAndIsActiveTrue(Long id);
        List<InvoiceComparisonEntity> findAllByIsActiveTrue();
        List<InvoiceComparisonEntity> findByComparisonStatusAndIsActiveTrue(InvoiceComparisonStatus status);
    }

    interface InvoiceLineItemMismatchJpaRepository
            extends JpaRepository<InvoiceLineItemMismatchEntity, Long> {
        List<InvoiceLineItemMismatchEntity> findByComparisonIdOrderByLineItemNumberAsc(Long comparisonId);
    }
}
