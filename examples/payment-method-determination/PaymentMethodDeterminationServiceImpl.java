package com.company.app.paymentmethod.service.impl;

import com.company.app.paymentmethod.dao.PaymentMethodDeterminationDao;
import com.company.app.paymentmethod.model.dto.*;
import com.company.app.paymentmethod.model.entity.PaymentMethodDeterminationEntity;
import com.company.app.paymentmethod.model.entity.PaymentRuleEntity;
import com.company.app.paymentmethod.model.enums.CustomerType;
import com.company.app.paymentmethod.model.enums.DeterminationStatus;
import com.company.app.paymentmethod.model.enums.PaymentMethodType;
import com.company.app.paymentmethod.service.PaymentMethodDeterminationService;
import com.company.app.exception.BusinessRuleException;
import com.company.app.exception.ResourceNotFoundException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Implementation of {@link PaymentMethodDeterminationService}.
 * Runs the rule-engine evaluation and manages overrides and rule configuration.
 */
@Service
@Transactional
public class PaymentMethodDeterminationServiceImpl
        implements PaymentMethodDeterminationService {

    private static final Logger log =
            LoggerFactory.getLogger(PaymentMethodDeterminationServiceImpl.class);

    private final PaymentMethodDeterminationDao dao;

    @Value("${app.payment-method-determination.default-method:CREDIT_CARD}")
    private String defaultMethod;

    public PaymentMethodDeterminationServiceImpl(PaymentMethodDeterminationDao dao) {
        this.dao = dao;
    }

    @Override
    public PaymentMethodDeterminationResponse determine(
            PaymentMethodDeterminationRequest request) {
        log.info("Determining payment method for transaction: {}", request.getTransactionId());

        // 1. Load all active rules ordered by priority
        List<PaymentRuleEntity> rules = dao.findAllActiveRulesOrderByPriority();

        // 2. First-match rule evaluation
        PaymentRuleEntity matchedRule = rules.stream()
                .filter(rule -> matches(rule, request))
                .findFirst()
                .orElse(null);

        // 3. Build determination entity
        PaymentMethodDeterminationEntity entity = new PaymentMethodDeterminationEntity();
        entity.setTransactionId(request.getTransactionId());
        entity.setAmount(request.getAmount());
        entity.setCurrency(request.getCurrency());
        entity.setCustomerType(request.getCustomerType());
        entity.setMerchantCategory(request.getMerchantCategory());
        entity.setCountry(request.getCountry());
        entity.setActive(true);

        if (matchedRule != null) {
            entity.setDeterminedMethod(matchedRule.getDeterminedMethod());
            entity.setRuleApplied(matchedRule.getRuleName());
            entity.setDeterminationStatus(DeterminationStatus.DETERMINED);
            log.info("Rule '{}' matched for transaction: {}",
                     matchedRule.getRuleName(), request.getTransactionId());
        } else {
            // Fallback to configured default
            entity.setDeterminedMethod(PaymentMethodType.valueOf(defaultMethod));
            entity.setRuleApplied("DEFAULT_FALLBACK");
            entity.setDeterminationStatus(DeterminationStatus.NO_RULE_MATCH);
            log.warn("No rule matched for transaction: {} — applying default: {}",
                     request.getTransactionId(), defaultMethod);
        }

        entity = dao.save(entity);
        return mapToResponse(entity);
    }

    @Override
    @Transactional(readOnly = true)
    public PaymentMethodDeterminationResponse getById(Long id) {
        return dao.findById(id)
                  .map(this::mapToResponse)
                  .orElseThrow(() -> new ResourceNotFoundException(
                      "Payment determination not found with id: " + id));
    }

    @Override
    @Transactional(readOnly = true)
    public PaymentMethodDeterminationResponse getByTransactionId(String transactionId) {
        return dao.findByTransactionId(transactionId)
                  .map(this::mapToResponse)
                  .orElseThrow(() -> new ResourceNotFoundException(
                      "Payment determination not found for transaction: " + transactionId));
    }

    @Override
    public PaymentMethodDeterminationResponse override(Long id,
            PaymentMethodOverrideRequest overrideRequest) {
        PaymentMethodDeterminationEntity entity = dao.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException(
                    "Payment determination not found with id: " + id));

        if (entity.getDeterminationStatus() == DeterminationStatus.OVERRIDDEN) {
            throw new BusinessRuleException("Determination has already been overridden");
        }

        entity.setDeterminedMethod(overrideRequest.getPaymentMethod());
        entity.setOverrideReason(overrideRequest.getReason());
        entity.setOverriddenBy(overrideRequest.getOverriddenBy());
        entity.setOverriddenAt(LocalDateTime.now());
        entity.setDeterminationStatus(DeterminationStatus.OVERRIDDEN);

        entity = dao.save(entity);
        log.info("Payment method overridden: id={}, method={}, by={}",
                 id, overrideRequest.getPaymentMethod(), overrideRequest.getOverriddenBy());
        return mapToResponse(entity);
    }

    @Override
    @Transactional(readOnly = true)
    public List<PaymentMethodDeterminationResponse> getHistory(
            CustomerType customerType, int page, int size) {
        return dao.findHistory(customerType, page, size)
                  .stream()
                  .map(this::mapToResponse)
                  .collect(Collectors.toList());
    }

    @Override
    @Transactional(readOnly = true)
    public List<PaymentRuleResponse> listRules() {
        return dao.findAllRules()
                  .stream()
                  .map(this::mapRuleToResponse)
                  .collect(Collectors.toList());
    }

    @Override
    public PaymentRuleResponse createRule(PaymentRuleRequest request) {
        PaymentRuleEntity rule = new PaymentRuleEntity();
        applyRuleRequest(rule, request);
        rule.setActive(true);
        rule = dao.saveRule(rule);
        log.info("Payment rule created: {}", rule.getRuleName());
        return mapRuleToResponse(rule);
    }

    @Override
    public PaymentRuleResponse updateRule(Long ruleId, PaymentRuleRequest request) {
        PaymentRuleEntity rule = dao.findRuleById(ruleId)
                .orElseThrow(() -> new ResourceNotFoundException(
                    "Payment rule not found with id: " + ruleId));
        applyRuleRequest(rule, request);
        rule = dao.saveRule(rule);
        log.info("Payment rule updated: {}", rule.getRuleName());
        return mapRuleToResponse(rule);
    }

    @Override
    public PaymentRuleResponse setRuleActive(Long ruleId, boolean active) {
        PaymentRuleEntity rule = dao.findRuleById(ruleId)
                .orElseThrow(() -> new ResourceNotFoundException(
                    "Payment rule not found with id: " + ruleId));
        rule.setActive(active);
        rule = dao.saveRule(rule);
        log.info("Payment rule {} {}", rule.getRuleName(), active ? "activated" : "deactivated");
        return mapRuleToResponse(rule);
    }

    // -------------------------------------------------------------------------
    // Private helpers
    // -------------------------------------------------------------------------

    private boolean matches(PaymentRuleEntity rule, PaymentMethodDeterminationRequest req) {
        if (rule.getCustomerType() != null
                && rule.getCustomerType() != req.getCustomerType()) return false;
        if (rule.getCurrency() != null
                && !rule.getCurrency().equalsIgnoreCase(req.getCurrency())) return false;
        if (rule.getCountry() != null
                && !rule.getCountry().equalsIgnoreCase(req.getCountry())) return false;
        if (rule.getMerchantCategory() != null
                && !rule.getMerchantCategory().equals(req.getMerchantCategory())) return false;
        if (rule.getMinAmount() != null
                && req.getAmount().compareTo(rule.getMinAmount()) < 0) return false;
        if (rule.getMaxAmount() != null
                && req.getAmount().compareTo(rule.getMaxAmount()) > 0) return false;
        return true;
    }

    private void applyRuleRequest(PaymentRuleEntity rule, PaymentRuleRequest request) {
        rule.setRuleName(request.getRuleName());
        rule.setPriority(request.getPriority());
        rule.setCustomerType(request.getCustomerType());
        rule.setMinAmount(request.getMinAmount());
        rule.setMaxAmount(request.getMaxAmount());
        rule.setCurrency(request.getCurrency());
        rule.setCountry(request.getCountry());
        rule.setMerchantCategory(request.getMerchantCategory());
        rule.setDeterminedMethod(request.getDeterminedMethod());
    }

    private PaymentMethodDeterminationResponse mapToResponse(
            PaymentMethodDeterminationEntity entity) {
        PaymentMethodDeterminationResponse r = new PaymentMethodDeterminationResponse();
        r.setId(entity.getId());
        r.setTransactionId(entity.getTransactionId());
        r.setAmount(entity.getAmount());
        r.setCurrency(entity.getCurrency());
        r.setCustomerType(entity.getCustomerType() != null
                          ? entity.getCustomerType().name() : null);
        r.setDeterminedMethod(entity.getDeterminedMethod() != null
                              ? entity.getDeterminedMethod().name() : null);
        r.setRuleApplied(entity.getRuleApplied());
        r.setDeterminationStatus(entity.getDeterminationStatus().name());
        r.setOverrideReason(entity.getOverrideReason());
        r.setOverriddenBy(entity.getOverriddenBy());
        r.setOverriddenAt(entity.getOverriddenAt());
        r.setCreatedAt(entity.getCreatedAt());
        return r;
    }

    private PaymentRuleResponse mapRuleToResponse(PaymentRuleEntity rule) {
        PaymentRuleResponse r = new PaymentRuleResponse();
        r.setId(rule.getId());
        r.setRuleName(rule.getRuleName());
        r.setPriority(rule.getPriority());
        r.setCustomerType(rule.getCustomerType() != null ? rule.getCustomerType().name() : null);
        r.setMinAmount(rule.getMinAmount());
        r.setMaxAmount(rule.getMaxAmount());
        r.setCurrency(rule.getCurrency());
        r.setCountry(rule.getCountry());
        r.setDeterminedMethod(rule.getDeterminedMethod().name());
        r.setActive(rule.isActive());
        return r;
    }
}
