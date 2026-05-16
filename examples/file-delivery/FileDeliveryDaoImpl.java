package com.company.app.filedelivery.dao.impl;

import com.company.app.filedelivery.dao.FileDeliveryDao;
import com.company.app.filedelivery.model.entity.FileDeliveryEntity;
import com.company.app.filedelivery.model.enums.FileDeliveryStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

/**
 * JPA-backed implementation of {@link FileDeliveryDao}.
 */
@Repository
public class FileDeliveryDaoImpl implements FileDeliveryDao {

    private final FileDeliveryJpaRepository jpaRepository;

    public FileDeliveryDaoImpl(FileDeliveryJpaRepository jpaRepository) {
        this.jpaRepository = jpaRepository;
    }

    @Override
    public FileDeliveryEntity save(FileDeliveryEntity entity) {
        return jpaRepository.save(entity);
    }

    @Override
    public Optional<FileDeliveryEntity> findById(Long id) {
        return jpaRepository.findByIdAndIsActiveTrue(id);
    }

    @Override
    public List<FileDeliveryEntity> findAll() {
        return jpaRepository.findAllByIsActiveTrue();
    }

    @Override
    public List<FileDeliveryEntity> findByUploadedBy(String uploadedBy) {
        return jpaRepository.findByUploadedByAndIsActiveTrue(uploadedBy);
    }

    @Override
    public List<FileDeliveryEntity> findByStatus(FileDeliveryStatus status) {
        return jpaRepository.findByStatusAndIsActiveTrue(status);
    }

    @Override
    public void deleteById(Long id) {
        // Soft delete handled in service — set status = DELETED, is_active = false
        jpaRepository.findById(id).ifPresent(entity -> {
            entity.setActive(false);
            jpaRepository.save(entity);
        });
    }

    @Override
    public boolean existsById(Long id) {
        return jpaRepository.existsByIdAndIsActiveTrue(id);
    }

    // -------------------------------------------------------------------------
    // Internal Spring Data JPA repository
    // -------------------------------------------------------------------------

    interface FileDeliveryJpaRepository extends JpaRepository<FileDeliveryEntity, Long> {
        Optional<FileDeliveryEntity> findByIdAndIsActiveTrue(Long id);
        List<FileDeliveryEntity> findAllByIsActiveTrue();
        List<FileDeliveryEntity> findByUploadedByAndIsActiveTrue(String uploadedBy);
        List<FileDeliveryEntity> findByStatusAndIsActiveTrue(FileDeliveryStatus status);
        boolean existsByIdAndIsActiveTrue(Long id);
    }
}
