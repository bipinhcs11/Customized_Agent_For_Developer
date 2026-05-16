package com.company.app.paymentmethod.dao.impl;

import com.company.app.paymentmethod.dao.PaymentMethodDeterminationDao;
import com.company.app.paymentmethod.model.entity.PaymentMethodDeterminationEntity;
import com.company.app.paymentmethod.model.entity.PaymentRuleEntity;
import com.company.app.paymentmethod.model.enums.CustomerType;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

/**
 * JPA-backed implementation of {@link PaymentMethodDeterminationDao}.
 */
@Repository
public class PaymentMethodDeterminationDaoImpl implements PaymentMethodDeterminationDao {

    private final PaymentMethodDeterminationJpaRepository determinationRepo;
    private final PaymentRuleJpaRepository ruleRepo;

    public PaymentMethodDeterminationDaoImpl(
            PaymentMethodDeterminationJpaRepository determinationRepo,
            PaymentRuleJpaRepository ruleRepo) {
        this.determinationRepo = determinationRepo;
        this.ruleRepo = ruleRepo;
    }

    @Override
    public PaymentMethodDeterminationEntity save(PaymentMethodDeterminationEntity entity) {
        return determinationRepo.save(entity);
    }

    @Override
    public Optional<PaymentMethodDeterminationEntity> findById(Long id) {
        return determinationRepo.findByIdAndIsActiveTrue(id);
    }

    @Override
    public Optional<PaymentMethodDeterminationEntity> findByTransactionId(String transactionId) {
        return determinationRepo.findByTransactionIdAndIsActiveTrue(transactionId);
    }

    @Override
    public List<PaymentMethodDeterminationEntity> findHistory(
            CustomerType customerType, int page, int size) {
        PageRequest pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
        if (customerType != null) {
            return determinationRepo
                    .findByCustomerTypeAndIsActiveTrue(customerType, pageable).getContent();
        }
        return determinationRepo.findAllByIsActiveTrue(pageable).getContent();
    }

    @Override
    public List<PaymentRuleEntity> findAllActiveRulesOrderByPriority() {
        return ruleRepo.findByIsActiveTrueOrderByPriorityAsc();
    }

    @Override
    public List<PaymentRuleEntity> findAllRules() {
        return ruleRepo.findAllByOrderByPriorityAsc();
    }

    @Override
    public Optional<PaymentRuleEntity> findRuleById(Long id) {
        return ruleRepo.findById(id);
    }

    @Override
    public PaymentRuleEntity saveRule(PaymentRuleEntity rule) {
        return ruleRepo.save(rule);
    }

    // -------------------------------------------------------------------------
    // Internal JPA repositories
    // -------------------------------------------------------------------------

    interface PaymentMethodDeterminationJpaRepository
            extends JpaRepository<PaymentMethodDeterminationEntity, Long> {
        Optional<PaymentMethodDeterminationEntity> findByIdAndIsActiveTrue(Long id);
        Optional<PaymentMethodDeterminationEntity> findByTransactionIdAndIsActiveTrue(String txId);
        org.springframework.data.domain.Page<PaymentMethodDeterminationEntity>
            findByCustomerTypeAndIsActiveTrue(CustomerType customerType,
                                             org.springframework.data.domain.Pageable pageable);
        org.springframework.data.domain.Page<PaymentMethodDeterminationEntity>
            findAllByIsActiveTrue(org.springframework.data.domain.Pageable pageable);
    }

    interface PaymentRuleJpaRepository extends JpaRepository<PaymentRuleEntity, Long> {
        List<PaymentRuleEntity> findByIsActiveTrueOrderByPriorityAsc();
        List<PaymentRuleEntity> findAllByOrderByPriorityAsc();
    }
}
