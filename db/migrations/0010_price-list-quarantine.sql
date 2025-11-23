-- 0010_price-list-quarantine.sql
--
-- Карантинная таблица для некорректных строк прайс-листа.
-- Используется в связке с Data Quality Gates (bad_df + DQ_ERRORS_COLUMN).

CREATE TABLE IF NOT EXISTS price_list_quarantine (
    id           bigserial PRIMARY KEY,
    envelope_id  uuid NOT NULL REFERENCES ingest_envelope(envelope_id),
    code         text,
    raw_row      jsonb NOT NULL,
    dq_errors    text[] NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Быстрый поиск по конкретному импортному файлу
CREATE INDEX IF NOT EXISTS idx_price_list_quarantine_env_created
    ON price_list_quarantine (envelope_id, created_at DESC);

-- Быстрый поиск по коду товара
CREATE INDEX IF NOT EXISTS idx_price_list_quarantine_code
    ON price_list_quarantine (code);

-- Поиск по типу/тексту ошибок (ANY(dq_errors) LIKE ... и т.п.)
CREATE INDEX IF NOT EXISTS idx_price_list_quarantine_dq_errors_gin
    ON price_list_quarantine USING gin (dq_errors);
