-- =====================================================================
-- Migration: Add Idempotency Tables
-- Issue: #80
-- Date: 2025-11-02
-- Author: glinozem
--
-- Purpose: Implement file fingerprinting to prevent duplicate imports
-- =====================================================================

-- =====================================================================
-- Table: ingest_envelope
-- Журнал всех импортов файлов
-- =====================================================================
CREATE TABLE IF NOT EXISTS ingest_envelope (
  envelope_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Информация о файле
  file_name TEXT NOT NULL,
  file_sha256 CHAR(64) NOT NULL,  -- SHA256 хеш (64 hex символа)
  file_path TEXT,                 -- Полный путь к файлу (опционально)
  file_size_bytes BIGINT,         -- Размер файла в байтах

  -- Метаданные импорта
  upload_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  processing_started_at TIMESTAMPTZ,
  processing_completed_at TIMESTAMPTZ,

  -- Результаты импорта
  rows_inserted INT DEFAULT 0,
  rows_updated INT DEFAULT 0,
  rows_failed INT DEFAULT 0,

  -- Статус
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'success', 'failed')),
  error_message TEXT,             -- Сообщение об ошибке при неудаче

  -- Дополнительные данные (JSON для расширяемости)
  metadata JSONB DEFAULT '{}'::jsonb
);

-- Уникальный constraint на SHA256 для предотвращения дубликатов
CREATE UNIQUE INDEX IF NOT EXISTS ux_ingest_envelope_sha256
  ON ingest_envelope(file_sha256);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_ingest_envelope_status
  ON ingest_envelope(status);

CREATE INDEX IF NOT EXISTS idx_ingest_envelope_timestamp
  ON ingest_envelope(upload_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_ingest_envelope_filename
  ON ingest_envelope(file_name);

-- Комментарии
COMMENT ON TABLE ingest_envelope IS
  'Журнал всех импортов файлов с SHA256 fingerprinting для идемпотентности';

COMMENT ON COLUMN ingest_envelope.file_sha256 IS
  'SHA256 хеш файла для обнаружения дубликатов';

COMMENT ON COLUMN ingest_envelope.status IS
  'pending: в очереди, processing: обрабатывается, success: успешно, failed: ошибка';

-- =====================================================================
-- Table: price_list
-- Связь импорта с эффективной датой прайса
-- =====================================================================
CREATE TABLE IF NOT EXISTS price_list (
  price_list_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Связь с импортом
  envelope_id UUID NOT NULL REFERENCES ingest_envelope(envelope_id) ON DELETE CASCADE,

  -- Эффективная дата прайса
  effective_date DATE NOT NULL,

  -- Дополнительная информация
  file_path TEXT,
  discount_percent NUMERIC(5,2),  -- Скидка, примененная к прайсу (например, 10.00)

  -- Метаданные
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  notes TEXT
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_price_list_envelope
  ON price_list(envelope_id);

CREATE INDEX IF NOT EXISTS idx_price_list_date
  ON price_list(effective_date DESC);

-- Уникальный constraint: один envelope может иметь только одну эффективную дату
CREATE UNIQUE INDEX IF NOT EXISTS ux_price_list_envelope_date
  ON price_list(envelope_id, effective_date);

-- Комментарии
COMMENT ON TABLE price_list IS
  'Связь между импортом файла и эффективной датой прайса';

COMMENT ON COLUMN price_list.effective_date IS
  'Дата, с которой действуют цены из этого прайс-листа';

COMMENT ON COLUMN price_list.discount_percent IS
  'Скидка, извлеченная из файла (например, из ячейки S5 в Excel)';

-- =====================================================================
-- Verification Queries
-- Запросы для проверки созданных таблиц
-- =====================================================================

-- Проверить, что таблицы созданы
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'ingest_envelope') THEN
    RAISE EXCEPTION 'Table ingest_envelope was not created!';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'price_list') THEN
    RAISE EXCEPTION 'Table price_list was not created!';
  END IF;

  RAISE NOTICE 'Migration completed successfully!';
END $$;
