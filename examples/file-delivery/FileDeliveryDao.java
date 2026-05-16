package com.company.app.filedelivery.dao;

import com.company.app.filedelivery.model.entity.FileDeliveryEntity;
import com.company.app.filedelivery.model.enums.FileDeliveryStatus;

import java.util.List;
import java.util.Optional;

/**
 * Data-access contract for File Delivery.
 */
public interface FileDeliveryDao {

    FileDeliveryEntity save(FileDeliveryEntity entity);

    Optional<FileDeliveryEntity> findById(Long id);

    List<FileDeliveryEntity> findAll();

    List<FileDeliveryEntity> findByUploadedBy(String uploadedBy);

    List<FileDeliveryEntity> findByStatus(FileDeliveryStatus status);

    void deleteById(Long id);

    boolean existsById(Long id);
}
