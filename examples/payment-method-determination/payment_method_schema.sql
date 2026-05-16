-- =============================================================================
-- Payment Method Determination Schema
-- =============================================================================

CREATE TABLE IF NOT EXISTS payment_method_determination (
    id                      BIGSERIAL PRIMARY KEY,
    transaction_id          VARCHAR(100)    NOT NULL UNIQUE,
    amount                  NUMERIC(18,2)   NOT NULL,
    currency                CHAR(3)         NOT NULL,
    customer_type           VARCHAR(30)     NOT NULL,
    merchant_category       VARCHAR(10),
    country                 CHAR(2),
    determined_method       VARCHAR(50),
    rule_applied            VARCHAR(200),
    determination_status    VARCHAR(30)     NOT NULL DEFAULT 'DETERMINED',
    override_reason         TEXT,
    overridden_by           VARCHAR(100),
    overridden_at           TIMESTAMP,

    -- Audit columns
    created_at              TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP       NOT NULL DEFAULT NOW(),
    created_by              VARCHAR(100),
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS payment_rule (
    id                  BIGSERIAL PRIMARY KEY,
    rule_name           VARCHAR(200)    NOT NULL UNIQUE,
    priority            INTEGER         NOT NULL,
    customer_type       VARCHAR(30),          -- NULL = any
    min_amount          NUMERIC(18,2),        -- NULL = no lower bound
    max_amount          NUMERIC(18,2),        -- NULL = no upper bound
    currency            CHAR(3),              -- NULL = any
    country             CHAR(2),              -- NULL = any
    merchant_category   VARCHAR(10),          -- NULL = any
    determined_method   VARCHAR(50)     NOT NULL,
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    created_by          VARCHAR(100)
);

-- Seed rules
INSERT INTO payment_rule (rule_name, priority, customer_type, min_amount, max_amount,
                           currency, country, determined_method)
VALUES
    ('Government large USD wire',  5,  'GOVERNMENT', 10000.00, NULL,     'USD', NULL, 'WIRE_TRANSFER'),
    ('Corporate high-value wire', 10,  'CORPORATE',  50000.00, NULL,     'USD', NULL, 'WIRE_TRANSFER'),
    ('EU individual SEPA',        20,  'INDIVIDUAL', NULL,     49999.99, 'EUR', NULL, 'SEPA'),
    ('US ACH standard',           30,  NULL,         NULL,     9999.99,  'USD', 'US', 'ACH'),
    ('Default credit card',       99,  NULL,         NULL,     NULL,     NULL,  NULL, 'CREDIT_CARD')
ON CONFLICT (rule_name) DO NOTHING;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_pmd_transaction_id
    ON payment_method_determination(transaction_id);

CREATE INDEX IF NOT EXISTS idx_pmd_determination_status
    ON payment_method_determination(determination_status);

CREATE INDEX IF NOT EXISTS idx_pmd_customer_type
    ON payment_method_determination(customer_type);

CREATE INDEX IF NOT EXISTS idx_pmd_created_at
    ON payment_method_determination(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pmd_is_active
    ON payment_method_determination(is_active) WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_payment_rule_priority
    ON payment_rule(priority) WHERE is_active = TRUE;

-- Auto-update triggers
CREATE OR REPLACE FUNCTION update_pmd_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_pmd_updated_at ON payment_method_determination;
CREATE TRIGGER trg_pmd_updated_at
    BEFORE UPDATE ON payment_method_determination
    FOR EACH ROW EXECUTE FUNCTION update_pmd_updated_at();

DROP TRIGGER IF EXISTS trg_payment_rule_updated_at ON payment_rule;
CREATE TRIGGER trg_payment_rule_updated_at
    BEFORE UPDATE ON payment_rule
    FOR EACH ROW EXECUTE FUNCTION update_pmd_updated_at();
