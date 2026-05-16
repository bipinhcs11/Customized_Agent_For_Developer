package com.company.app.paymentmethod.controller;

import com.company.app.paymentmethod.model.dto.*;
import com.company.app.paymentmethod.model.enums.CustomerType;
import com.company.app.paymentmethod.service.PaymentMethodDeterminationService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * REST controller for Payment Method Determination.
 * Handles determination requests, overrides, history, and rule management.
 */
@RestController
@RequestMapping("/api/v1/payment-method-determination")
@Validated
public class PaymentMethodDeterminationController {

    private final PaymentMethodDeterminationService service;

    public PaymentMethodDeterminationController(PaymentMethodDeterminationService service) {
        this.service = service;
    }

    /**
     * Determine the payment method for a transaction.
     */
    @PostMapping("/determine")
    public ResponseEntity<PaymentMethodDeterminationResponse> determine(
            @Valid @RequestBody PaymentMethodDeterminationRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.determine(request));
    }

    /**
     * Retrieve a determination result by ID.
     */
    @GetMapping("/{id}")
    public ResponseEntity<PaymentMethodDeterminationResponse> getById(@PathVariable Long id) {
        return ResponseEntity.ok(service.getById(id));
    }

    /**
     * Retrieve a determination by transaction ID.
     */
    @GetMapping("/transaction/{transactionId}")
    public ResponseEntity<PaymentMethodDeterminationResponse> getByTransactionId(
            @PathVariable String transactionId) {
        return ResponseEntity.ok(service.getByTransactionId(transactionId));
    }

    /**
     * Override the determined payment method for a transaction.
     */
    @PutMapping("/{id}/override")
    public ResponseEntity<PaymentMethodDeterminationResponse> override(
            @PathVariable Long id,
            @Valid @RequestBody PaymentMethodOverrideRequest overrideRequest) {
        return ResponseEntity.ok(service.override(id, overrideRequest));
    }

    /**
     * Get determination history with optional filters.
     */
    @GetMapping("/history")
    public ResponseEntity<List<PaymentMethodDeterminationResponse>> getHistory(
            @RequestParam(required = false) CustomerType customerType,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ResponseEntity.ok(service.getHistory(customerType, page, size));
    }

    // --- Rule Management ---

    /**
     * List all payment determination rules.
     */
    @GetMapping("/rules")
    public ResponseEntity<List<PaymentRuleResponse>> listRules() {
        return ResponseEntity.ok(service.listRules());
    }

    /**
     * Create a new payment determination rule.
     */
    @PostMapping("/rules")
    public ResponseEntity<PaymentRuleResponse> createRule(
            @Valid @RequestBody PaymentRuleRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.createRule(request));
    }

    /**
     * Update an existing payment determination rule.
     */
    @PutMapping("/rules/{ruleId}")
    public ResponseEntity<PaymentRuleResponse> updateRule(
            @PathVariable Long ruleId,
            @Valid @RequestBody PaymentRuleRequest request) {
        return ResponseEntity.ok(service.updateRule(ruleId, request));
    }

    /**
     * Activate or deactivate a rule.
     */
    @PatchMapping("/rules/{ruleId}/active")
    public ResponseEntity<PaymentRuleResponse> setRuleActive(
            @PathVariable Long ruleId,
            @RequestParam boolean active) {
        return ResponseEntity.ok(service.setRuleActive(ruleId, active));
    }
}
