package com.company.app.paymentmethod.service;

import com.company.app.paymentmethod.model.dto.*;
import com.company.app.paymentmethod.model.enums.CustomerType;

import java.util.List;

/**
 * Business service contract for Payment Method Determination.
 */
public interface PaymentMethodDeterminationService {

    /**
     * Evaluates the transaction context against all active rules and determines
     * the appropriate payment method.
     *
     * @param request the transaction context
     * @return the determination result
     */
    PaymentMethodDeterminationResponse determine(PaymentMethodDeterminationRequest request);

    /**
     * Retrieves a determination by its internal ID.
     */
    PaymentMethodDeterminationResponse getById(Long id);

    /**
     * Retrieves a determination by the external transaction ID.
     */
    PaymentMethodDeterminationResponse getByTransactionId(String transactionId);

    /**
     * Manually overrides the determined payment method for a transaction.
     *
     * @param id              the determination ID
     * @param overrideRequest the override details
     * @return the updated determination
     */
    PaymentMethodDeterminationResponse override(Long id, PaymentMethodOverrideRequest overrideRequest);

    /**
     * Returns determination history, optionally filtered by customer type.
     */
    List<PaymentMethodDeterminationResponse> getHistory(CustomerType customerType, int page, int size);

    // --- Rule Management ---

    List<PaymentRuleResponse> listRules();

    PaymentRuleResponse createRule(PaymentRuleRequest request);

    PaymentRuleResponse updateRule(Long ruleId, PaymentRuleRequest request);

    PaymentRuleResponse setRuleActive(Long ruleId, boolean active);
}
