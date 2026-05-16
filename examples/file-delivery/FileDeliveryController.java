package com.company.app.filedelivery.controller;

import com.company.app.filedelivery.model.dto.FileDeliveryResponse;
import com.company.app.filedelivery.model.dto.FileDeliveryStatusResponse;
import com.company.app.filedelivery.service.FileDeliveryService;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

/**
 * REST controller for File Delivery operations.
 * Handles file upload, download, status tracking, and delivery management.
 */
@RestController
@RequestMapping("/api/v1/file-delivery")
@Validated
public class FileDeliveryController {

    private final FileDeliveryService fileDeliveryService;

    public FileDeliveryController(FileDeliveryService fileDeliveryService) {
        this.fileDeliveryService = fileDeliveryService;
    }

    /**
     * Upload a new file for delivery.
     */
    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<FileDeliveryResponse> upload(
            @RequestParam("file") MultipartFile file,
            @RequestParam String deliveredTo,
            @RequestParam(required = false) String uploadedBy) {
        FileDeliveryResponse response = fileDeliveryService.upload(file, deliveredTo, uploadedBy);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    /**
     * Retrieve file delivery record by ID.
     */
    @GetMapping("/{id}")
    public ResponseEntity<FileDeliveryResponse> getById(@PathVariable Long id) {
        return ResponseEntity.ok(fileDeliveryService.getById(id));
    }

    /**
     * Download the file associated with a delivery record.
     */
    @GetMapping("/{id}/download")
    public ResponseEntity<Resource> download(@PathVariable Long id) {
        FileDeliveryService.DownloadResult result = fileDeliveryService.download(id);
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"" + result.getFileName() + "\"")
                .contentType(MediaType.parseMediaType(result.getContentType()))
                .body(result.getResource());
    }

    /**
     * Get just the status of a file delivery.
     */
    @GetMapping("/{id}/status")
    public ResponseEntity<FileDeliveryStatusResponse> getStatus(@PathVariable Long id) {
        return ResponseEntity.ok(fileDeliveryService.getStatus(id));
    }

    /**
     * List all file deliveries uploaded by a specific user.
     */
    @GetMapping("/user/{uploadedBy}")
    public ResponseEntity<List<FileDeliveryResponse>> getByUploader(
            @PathVariable String uploadedBy) {
        return ResponseEntity.ok(fileDeliveryService.getByUploader(uploadedBy));
    }

    /**
     * Acknowledge receipt of a delivered file.
     */
    @PutMapping("/{id}/acknowledge")
    public ResponseEntity<FileDeliveryResponse> acknowledge(@PathVariable Long id) {
        return ResponseEntity.ok(fileDeliveryService.acknowledge(id));
    }

    /**
     * Soft-delete a file delivery record.
     */
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        fileDeliveryService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
