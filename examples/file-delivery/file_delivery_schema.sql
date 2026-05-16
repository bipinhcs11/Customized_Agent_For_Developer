-- =============================================================================
-- File Delivery Schema
-- =============================================================================

CREATE TABLE IF NOT EXISTS file_delivery (
    id                  BIGSERIAL PRIMARY KEY,
    file_name           VARCHAR(500)    NOT NULL,
    file_type           VARCHAR(100)    NOT NULL,
    file_size_bytes     BIGINT          NOT NULL,
    storage_path        VARCHAR(1000)   NOT NULL UNIQUE,
    checksum            VARCHAR(64),
    status              VARCHAR(30)     NOT NULL DEFAULT 'PENDING',
    uploaded_by         VARCHAR(100)    NOT NULL,
    delivered_to        VARCHAR(100),
    delivered_at        TIMESTAMP,
    expires_at          TIMESTAMP,
    download_count      INTEGER         NOT NULL DEFAULT 0,

    -- Audit columns
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    created_by          VARCHAR(100),
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_file_delivery_status
    ON file_delivery(status);

CREATE INDEX IF NOT EXISTS idx_file_delivery_uploaded_by
    ON file_delivery(uploaded_by);

CREATE INDEX IF NOT EXISTS idx_file_delivery_delivered_to
    ON file_delivery(delivered_to);

CREATE INDEX IF NOT EXISTS idx_file_delivery_expires_at
    ON file_delivery(expires_at)
    WHERE status IN ('READY', 'PENDING');

CREATE INDEX IF NOT EXISTS idx_file_delivery_is_active
    ON file_delivery(is_active)
    WHERE is_active = TRUE;

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION update_file_delivery_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_file_delivery_updated_at ON file_delivery;

CREATE TRIGGER trg_file_delivery_updated_at
    BEFORE UPDATE ON file_delivery
    FOR EACH ROW EXECUTE FUNCTION update_file_delivery_updated_at();
