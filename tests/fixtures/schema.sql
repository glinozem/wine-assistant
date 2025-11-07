-- =====================================================================
-- Minimal CI schema — idempotency envelopes & price_list
-- =====================================================================

-- UUID helpers for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Чистый старт для повторных CI-прогонов
DROP TABLE IF EXISTS public.price_list CASCADE;
DROP TABLE IF EXISTS public.ingest_envelope CASCADE;

-- =========================
-- Таблица-пакет (envelope)
-- =========================
CREATE TABLE public.ingest_envelope (
    envelope_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name             VARCHAR(255) NOT NULL,
    file_sha256           VARCHAR(64) NOT NULL UNIQUE,
    file_path             TEXT,
    file_size_bytes       BIGINT,

    status                VARCHAR(20) DEFAULT 'processing'
                          CHECK (status IN ('processing', 'success', 'failed')),

    upload_timestamp      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    processing_completed_at TIMESTAMPTZ,

    rows_inserted         INT DEFAULT 0,
    rows_updated          INT DEFAULT 0,
    rows_failed           INT DEFAULT 0,

    error_message         TEXT,

    created_at            TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- Метаданные прайс-листа
-- =========================
CREATE TABLE public.price_list (
    price_list_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    envelope_id       UUID NOT NULL REFERENCES public.ingest_envelope(envelope_id) ON DELETE CASCADE,
    supplier_code     VARCHAR(100),
    file_path         TEXT,
    effective_date    DATE,
    asof_date         DATE,
    discount_percent  DECIMAL(6,4),
    rows_count        INT DEFAULT 0,
    created_at        TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- Индексы
-- =========================
CREATE INDEX IF NOT EXISTS idx_ingest_envelope_sha256          ON public.ingest_envelope(file_sha256);
CREATE INDEX IF NOT EXISTS idx_ingest_envelope_status          ON public.ingest_envelope(status);
CREATE INDEX IF NOT EXISTS idx_ingest_envelope_created_at      ON public.ingest_envelope(created_at);
CREATE INDEX IF NOT EXISTS idx_ingest_envelope_upload_timestamp ON public.ingest_envelope(upload_timestamp);

CREATE INDEX IF NOT EXISTS idx_price_list_envelope_id          ON public.price_list(envelope_id);
CREATE INDEX IF NOT EXISTS idx_price_list_asof_date            ON public.price_list(asof_date);
CREATE INDEX IF NOT EXISTS idx_price_list_effective_date       ON public.price_list(effective_date);

-- =========================
-- Триггеры updated_at
-- =========================
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_update_ingest_envelope_updated_at
BEFORE UPDATE ON public.ingest_envelope
FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER trg_update_price_list_updated_at
BEFORE UPDATE ON public.price_list
FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Права (для CI-пользователя postgres)
GRANT ALL PRIVILEGES ON TABLE public.ingest_envelope TO postgres;
GRANT ALL PRIVILEGES ON TABLE public.price_list TO postgres;
