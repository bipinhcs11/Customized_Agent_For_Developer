package com.company.app.invoicecompare.controller;

import com.company.app.invoicecompare.model.dto.*;
import com.company.app.invoicecompare.model.enums.InvoiceComparisonStatus;
import com.company.app.invoicecompare.service.InvoiceCompareService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * REST controller for Invoice Compare operations.
 * Handles comparison requests, result retrieval, and review workflow.
 */
@RestController
@RequestMapping("/api/v1/invoice-compare")
@Validated
public class InvoiceCompareController {

    private final InvoiceCompareService invoiceCompareService;

    public InvoiceCompareController(InvoiceCompareService invoiceCompareService) {
        this.invoiceCompareService = invoiceCompareService;
    }

    /**
     * Initiate a new invoice comparison.
     */
    @PostMapping("/compare")
    public ResponseEntity<InvoiceCompareResponse> compare(
            @Valid @RequestBody InvoiceCompareRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                             .body(invoiceCompareService.compare(request));
    }

    /**
     * Retrieve a comparison result by ID.
     */
    @GetMapping("/{id}")
    public ResponseEntity<InvoiceCompareResponse> getById(@PathVariable Long id) {
        return ResponseEntity.ok(invoiceCompareService.getById(id));
    }

    /**
     * Get all line-item mismatches for a comparison.
     */
    @GetMapping("/{id}/mismatches")
    public ResponseEntity<List<InvoiceLineItemMismatchResponse>> getMismatches(
            @PathVariable Long id) {
        return ResponseEntity.ok(invoiceCompareService.getMismatches(id));
    }

    /**
     * Approve a completed comparison.
     */
    @PutMapping("/{id}/approve")
    public ResponseEntity<InvoiceCompareResponse> approve(
            @PathVariable Long id,
            @RequestParam String reviewedBy,
            @RequestParam(required = false) String notes) {
        return ResponseEntity.ok(invoiceCompareService.approve(id, reviewedBy, notes));
    }

    /**
     * Reject a completed comparison.
     */
    @PutMapping("/{id}/reject")
    public ResponseEntity<InvoiceCompareResponse> reject(
            @PathVariable Long id,
            @RequestParam String reviewedBy,
            @RequestParam String notes) {
        return ResponseEntity.ok(invoiceCompareService.reject(id, reviewedBy, notes));
    }

    /**
     * List comparisons by status.
     */
    @GetMapping
    public ResponseEntity<List<InvoiceCompareResponse>> getByStatus(
            @RequestParam(required = false) InvoiceComparisonStatus status) {
        return ResponseEntity.ok(invoiceCompareService.getByStatus(status));
    }
}
