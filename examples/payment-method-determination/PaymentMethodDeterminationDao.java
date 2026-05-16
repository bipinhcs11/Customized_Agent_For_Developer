package com.company.app.paymentmethod.dao;

import com.company.app.paymentmethod.model.entity.PaymentMethodDeterminationEntity;
import com.company.app.paymentmethod.model.entity.PaymentRuleEntity;
import com.company.app.paymentmethod.model.enums.CustomerType;

import java.util.List;
import java.util.Optional;

/**
 * Data-access contract for Payment Method Determination.
 */
public interface PaymentMethodDeterminationDao {

    PaymentMethodDeterminationEntity save(PaymentMethodDeterminationEntity entity);

    Optional<PaymentMethodDeterminationEntity> findById(Long id);

    Optional<PaymentMethodDeterminationEntity> findByTransactionId(String transactionId);

    List<PaymentMethodDeterminationEntity> findHistory(CustomerType customerType, int page, int size);

    // Rules

    List<PaymentRuleEntity> findAllActiveRulesOrderByPriority();

    List<PaymentRuleEntity> findAllRules();

    Optional<PaymentRuleEntity> findRuleById(Long id);

    PaymentRuleEntity saveRule(PaymentRuleEntity rule);
}
