-- Minimal test database schema for CI
-- Tables required for idempotency tests (Issue #80, Issue #91)

-- UUID helpers for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Drop tables if exist (for clean CI runs)
DROP TABLE IF EXISTS price_list CASCADE;
DROP TABLE IF EXISTS ingest_envelope CASCADE;

-- Main envelope tracking table for ETL idempotency
CREATE TABLE ingest_envelope (
    envelope_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name VARCHAR(255) NOT NULL,
    file_sha256 VARCHAR(64) NOT NULL UNIQUE,
    file_path TEXT,
    file_size_bytes BIGINT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'success', 'failed')),
    upload_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processing_completed_at TIMESTAMP WITH TIME ZONE,
    rows_inserted INT DEFAULT 0,
    rows_updated INT DEFAULT 0,
    rows_failed INT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Price list metadata table
CREATE TABLE price_list (
    price_list_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    envelope_id UUID NOT NULL REFERENCES ingest_envelope(envelope_id) ON DELETE CASCADE,
    supplier_code VARCHAR(100),
    file_path TEXT,
    effective_date DATE,
    asof_date DATE,
    discount_percent DECIMAL(6,4),
    rows_count INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_ingest_envelope_sha256 ON ingest_envelope(file_sha256);
CREATE INDEX idx_ingest_envelope_status ON ingest_envelope(status);
CREATE INDEX idx_ingest_envelope_created_at ON ingest_envelope(created_at);
CREATE INDEX idx_ingest_envelope_upload_timestamp ON ingest_envelope(upload_timestamp);
CREATE INDEX idx_price_list_envelope_id ON price_list(envelope_id);
CREATE INDEX idx_price_list_asof_date ON price_list(asof_date);
CREATE INDEX idx_price_list_effective_date ON price_list(effective_date);

-- Trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_ingest_envelope_updated_at
    BEFORE UPDATE ON ingest_envelope
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_price_list_updated_at
    BEFORE UPDATE ON price_list
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions (for CI user 'postgres')
GRANT ALL PRIVILEGES ON TABLE ingest_envelope TO postgres;
GRANT ALL PRIVILEGES ON TABLE price_list TO postgres;
