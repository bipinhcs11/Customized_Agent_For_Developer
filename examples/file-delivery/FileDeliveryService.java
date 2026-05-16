package com.company.app.filedelivery.service;

import com.company.app.filedelivery.model.dto.FileDeliveryResponse;
import com.company.app.filedelivery.model.dto.FileDeliveryStatusResponse;
import org.springframework.core.io.Resource;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

/**
 * Business service contract for File Delivery.
 */
public interface FileDeliveryService {

    /**
     * Uploads a file and creates a delivery record in PENDING status.
     *
     * @param file        the file to upload
     * @param deliveredTo recipient identifier
     * @param uploadedBy  uploader identifier (user or system)
     * @return the created file delivery response
     */
    FileDeliveryResponse upload(MultipartFile file, String deliveredTo, String uploadedBy);

    /**
     * Retrieves a file delivery record by ID.
     *
     * @param id the delivery ID
     * @return the file delivery response
     */
    FileDeliveryResponse getById(Long id);

    /**
     * Downloads the file and increments download count.
     * Transitions status to DELIVERED on first download.
     *
     * @param id the delivery ID
     * @return a DownloadResult containing the resource and metadata
     */
    DownloadResult download(Long id);

    /**
     * Returns the current status of a file delivery.
     *
     * @param id the delivery ID
     * @return the status response
     */
    FileDeliveryStatusResponse getStatus(Long id);

    /**
     * Retrieves all file deliveries uploaded by a specific user.
     *
     * @param uploadedBy the uploader identifier
     * @return list of matching file delivery responses
     */
    List<FileDeliveryResponse> getByUploader(String uploadedBy);

    /**
     * Marks a file delivery as ACKNOWLEDGED by the recipient.
     *
     * @param id the delivery ID
     * @return the updated file delivery response
     */
    FileDeliveryResponse acknowledge(Long id);

    /**
     * Soft-deletes a file delivery record.
     *
     * @param id the delivery ID
     */
    void delete(Long id);

    /**
     * Value object returned by the download operation.
     */
    class DownloadResult {
        private final Resource resource;
        private final String fileName;
        private final String contentType;

        public DownloadResult(Resource resource, String fileName, String contentType) {
            this.resource = resource;
            this.fileName = fileName;
            this.contentType = contentType;
        }

        public Resource getResource() { return resource; }
        public String getFileName() { return fileName; }
        public String getContentType() { return contentType; }
    }
}
