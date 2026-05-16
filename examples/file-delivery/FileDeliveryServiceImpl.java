package com.company.app.filedelivery.service.impl;

import com.company.app.filedelivery.dao.FileDeliveryDao;
import com.company.app.filedelivery.model.dto.FileDeliveryResponse;
import com.company.app.filedelivery.model.dto.FileDeliveryStatusResponse;
import com.company.app.filedelivery.model.entity.FileDeliveryEntity;
import com.company.app.filedelivery.model.enums.FileDeliveryStatus;
import com.company.app.filedelivery.service.FileDeliveryService;
import com.company.app.exception.BusinessRuleException;
import com.company.app.exception.ResourceNotFoundException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.core.io.UrlResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.net.MalformedURLException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Implementation of {@link FileDeliveryService}.
 * Manages file upload, storage, status tracking, and delivery operations.
 */
@Service
@Transactional
public class FileDeliveryServiceImpl implements FileDeliveryService {

    private static final Logger log = LoggerFactory.getLogger(FileDeliveryServiceImpl.class);

    private final FileDeliveryDao fileDeliveryDao;

    @Value("${app.file-delivery.storage.base-path:/var/files/delivery}")
    private String basePath;

    @Value("${app.file-delivery.max-size-mb:100}")
    private int maxSizeMb;

    @Value("${app.file-delivery.expiry-days:7}")
    private int expiryDays;

    public FileDeliveryServiceImpl(FileDeliveryDao fileDeliveryDao) {
        this.fileDeliveryDao = fileDeliveryDao;
    }

    @Override
    public FileDeliveryResponse upload(MultipartFile file, String deliveredTo, String uploadedBy) {
        log.info("Uploading file: {} for recipient: {}", file.getOriginalFilename(), deliveredTo);

        // Validate file
        validateFile(file);

        // Compute storage path
        String storagePath = generateStoragePath(file.getOriginalFilename());

        // Write file to disk
        storeFile(file, storagePath);

        // Compute checksum
        String checksum = computeChecksum(file);

        // Build and persist entity
        FileDeliveryEntity entity = new FileDeliveryEntity();
        entity.setFileName(file.getOriginalFilename());
        entity.setFileType(file.getContentType());
        entity.setFileSizeBytes(file.getSize());
        entity.setStoragePath(storagePath);
        entity.setChecksum(checksum);
        entity.setStatus(FileDeliveryStatus.PENDING);
        entity.setUploadedBy(uploadedBy != null ? uploadedBy : "SYSTEM");
        entity.setDeliveredTo(deliveredTo);
        entity.setExpiresAt(LocalDateTime.now().plusDays(expiryDays));
        entity.setDownloadCount(0);
        entity.setActive(true);

        entity = fileDeliveryDao.save(entity);
        log.info("File delivery created with id: {}", entity.getId());

        return mapToResponse(entity);
    }

    @Override
    @Transactional(readOnly = true)
    public FileDeliveryResponse getById(Long id) {
        return fileDeliveryDao.findById(id)
                .map(this::mapToResponse)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "File delivery not found with id: " + id));
    }

    @Override
    public DownloadResult download(Long id) {
        FileDeliveryEntity entity = fileDeliveryDao.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "File delivery not found with id: " + id));

        if (!entity.getStatus().isDeliverable()) {
            throw new BusinessRuleException(
                    "File is not available for download. Current status: " + entity.getStatus());
        }

        // Load resource
        Resource resource = loadFileAsResource(entity.getStoragePath());

        // Update status and download count
        entity.setDownloadCount(entity.getDownloadCount() + 1);
        if (entity.getStatus() == FileDeliveryStatus.READY) {
            entity.setStatus(FileDeliveryStatus.DELIVERED);
            entity.setDeliveredAt(LocalDateTime.now());
        }
        fileDeliveryDao.save(entity);

        log.info("File downloaded: id={}, fileName={}, downloadCount={}",
                 id, entity.getFileName(), entity.getDownloadCount());

        return new DownloadResult(resource, entity.getFileName(), entity.getFileType());
    }

    @Override
    @Transactional(readOnly = true)
    public FileDeliveryStatusResponse getStatus(Long id) {
        FileDeliveryEntity entity = fileDeliveryDao.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "File delivery not found with id: " + id));
        FileDeliveryStatusResponse response = new FileDeliveryStatusResponse();
        response.setId(entity.getId());
        response.setFileName(entity.getFileName());
        response.setStatus(entity.getStatus().name());
        response.setDownloadCount(entity.getDownloadCount());
        response.setExpiresAt(entity.getExpiresAt());
        return response;
    }

    @Override
    @Transactional(readOnly = true)
    public List<FileDeliveryResponse> getByUploader(String uploadedBy) {
        return fileDeliveryDao.findByUploadedBy(uploadedBy)
                .stream()
                .map(this::mapToResponse)
                .collect(Collectors.toList());
    }

    @Override
    public FileDeliveryResponse acknowledge(Long id) {
        FileDeliveryEntity entity = fileDeliveryDao.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "File delivery not found with id: " + id));

        if (entity.getStatus() != FileDeliveryStatus.DELIVERED) {
            throw new BusinessRuleException(
                    "Cannot acknowledge — file is not in DELIVERED state: " + entity.getStatus());
        }

        entity.setStatus(FileDeliveryStatus.ACKNOWLEDGED);
        entity = fileDeliveryDao.save(entity);
        log.info("File delivery acknowledged: id={}", id);
        return mapToResponse(entity);
    }

    @Override
    public void delete(Long id) {
        FileDeliveryEntity entity = fileDeliveryDao.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "File delivery not found with id: " + id));
        entity.setStatus(FileDeliveryStatus.DELETED);
        entity.setActive(false);
        fileDeliveryDao.save(entity);
        log.info("File delivery soft-deleted: id={}", id);
        // Storage cleanup is handled asynchronously
    }

    // -------------------------------------------------------------------------
    // Private helpers
    // -------------------------------------------------------------------------

    private void validateFile(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new BusinessRuleException("File must not be empty");
        }
        long maxBytes = (long) maxSizeMb * 1024 * 1024;
        if (file.getSize() > maxBytes) {
            throw new BusinessRuleException(
                    "File size exceeds maximum allowed size of " + maxSizeMb + " MB");
        }
    }

    private String generateStoragePath(String originalFileName) {
        String extension = "";
        if (originalFileName != null && originalFileName.contains(".")) {
            extension = originalFileName.substring(originalFileName.lastIndexOf("."));
        }
        return UUID.randomUUID().toString().replace("-", "") + extension;
    }

    private void storeFile(MultipartFile file, String storagePath) {
        try {
            Path destination = Paths.get(basePath).resolve(storagePath).normalize();
            Files.createDirectories(destination.getParent());
            file.transferTo(destination.toFile());
        } catch (IOException e) {
            throw new BusinessRuleException("Failed to store file: " + e.getMessage());
        }
    }

    private Resource loadFileAsResource(String storagePath) {
        try {
            Path filePath = Paths.get(basePath).resolve(storagePath).normalize();
            Resource resource = new UrlResource(filePath.toUri());
            if (resource.exists()) return resource;
            throw new ResourceNotFoundException("File not found in storage: " + storagePath);
        } catch (MalformedURLException e) {
            throw new ResourceNotFoundException("File path is invalid: " + storagePath);
        }
    }

    private String computeChecksum(MultipartFile file) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(file.getBytes());
            return HexFormat.of().formatHex(hash);
        } catch (Exception e) {
            log.warn("Failed to compute checksum: {}", e.getMessage());
            return null;
        }
    }

    private FileDeliveryResponse mapToResponse(FileDeliveryEntity entity) {
        FileDeliveryResponse response = new FileDeliveryResponse();
        response.setId(entity.getId());
        response.setFileName(entity.getFileName());
        response.setFileType(entity.getFileType());
        response.setFileSizeBytes(entity.getFileSizeBytes());
        response.setStatus(entity.getStatus().name());
        response.setUploadedBy(entity.getUploadedBy());
        response.setDeliveredTo(entity.getDeliveredTo());
        response.setDeliveredAt(entity.getDeliveredAt());
        response.setExpiresAt(entity.getExpiresAt());
        response.setDownloadCount(entity.getDownloadCount());
        response.setCreatedAt(entity.getCreatedAt());
        return response;
    }
}
