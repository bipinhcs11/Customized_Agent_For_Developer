-- =============================================================================
-- Invoice Compare Schema
-- =============================================================================

CREATE TABLE IF NOT EXISTS invoice_comparison (
    id                      BIGSERIAL PRIMARY KEY,
    source_invoice_id       VARCHAR(100)    NOT NULL,
    target_invoice_id       VARCHAR(100)    NOT NULL,
    source_system           VARCHAR(50)     NOT NULL,
    target_system           VARCHAR(50)     NOT NULL,
    comparison_status       VARCHAR(30)     NOT NULL DEFAULT 'PENDING',
    total_mismatch_count    INTEGER         NOT NULL DEFAULT 0,
    total_amount_diff       NUMERIC(18,2),
    reconciled_notes        TEXT,
    reviewed_by             VARCHAR(100),
    reviewed_at             TIMESTAMP,

    -- Audit columns
    created_at              TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP       NOT NULL DEFAULT NOW(),
    created_by              VARCHAR(100),
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS invoice_line_item_mismatch (
    id                  BIGSERIAL PRIMARY KEY,
    comparison_id       BIGINT          NOT NULL REFERENCES invoice_comparison(id)
                            ON DELETE CASCADE,
    line_item_number    INTEGER         NOT NULL,
    mismatch_type       VARCHAR(50)     NOT NULL,
    field_name          VARCHAR(100),
    source_value        VARCHAR(500),
    target_value        VARCHAR(500),
    diff_amount         NUMERIC(18,2),
    resolved            BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_invoice_comparison_status
    ON invoice_comparison(comparison_status);

CREATE INDEX IF NOT EXISTS idx_invoice_comparison_source
    ON invoice_comparison(source_invoice_id);

CREATE INDEX IF NOT EXISTS idx_invoice_comparison_target
    ON invoice_comparison(target_invoice_id);

CREATE INDEX IF NOT EXISTS idx_invoice_comparison_is_active
    ON invoice_comparison(is_active) WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_invoice_mismatch_comparison_id
    ON invoice_line_item_mismatch(comparison_id);

CREATE INDEX IF NOT EXISTS idx_invoice_mismatch_type
    ON invoice_line_item_mismatch(mismatch_type);

CREATE INDEX IF NOT EXISTS idx_invoice_mismatch_unresolved
    ON invoice_line_item_mismatch(comparison_id, resolved)
    WHERE resolved = FALSE;

-- Auto-update trigger
CREATE OR REPLACE FUNCTION update_invoice_comparison_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_invoice_comparison_updated_at ON invoice_comparison;

CREATE TRIGGER trg_invoice_comparison_updated_at
    BEFORE UPDATE ON invoice_comparison
    FOR EACH ROW EXECUTE FUNCTION update_invoice_comparison_updated_at();
