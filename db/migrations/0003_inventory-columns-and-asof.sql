-- =====================================================================
-- Inventory columns normalization: add stock_total, reserved, stock_free, asof_date
-- =====================================================================

-- Добавляем новые колонки в inventory (если их нет)
ALTER TABLE inventory ADD COLUMN IF NOT EXISTS stock_total NUMERIC;
ALTER TABLE inventory ADD COLUMN IF NOT EXISTS reserved    NUMERIC;
ALTER TABLE inventory ADD COLUMN IF NOT EXISTS stock_free  NUMERIC;
ALTER TABLE inventory ADD COLUMN IF NOT EXISTS asof_date   DATE;

-- Миграция данных: если есть старая колонка qty, переносим её в stock_total
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'inventory' AND column_name = 'qty'
  ) THEN
    UPDATE inventory SET stock_total = qty WHERE stock_total IS NULL AND qty IS NOT NULL;
  END IF;
END $$;

-- Удаляем устаревшие колонки (если они есть)
ALTER TABLE inventory DROP COLUMN IF EXISTS qty;
ALTER TABLE inventory DROP COLUMN IF EXISTS in_stock;

-- Индекс на stock_free (если ещё нет)
CREATE INDEX IF NOT EXISTS idx_inventory_code_free ON inventory(code, stock_free);

-- Пересоздаём функцию upsert_inventory с правильной логикой
CREATE OR REPLACE FUNCTION upsert_inventory(
  p_code text,
  p_stock_total numeric,
  p_reserved numeric,
  p_stock_free numeric,
  p_as_of timestamp without time zone
) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  -- Запись в историю
  INSERT INTO inventory_history(code, stock_total, reserved, stock_free, as_of)
  VALUES (p_code, p_stock_total, p_reserved, p_stock_free, p_as_of);

  -- Обновление текущих остатков (с asof_date и updated_at)
  INSERT INTO inventory(code, stock_total, reserved, stock_free, asof_date)
  VALUES (p_code, p_stock_total, p_reserved, p_stock_free, p_as_of::date)
  ON CONFLICT (code) DO UPDATE
  SET stock_total = EXCLUDED.stock_total,
      reserved    = EXCLUDED.reserved,
      stock_free  = EXCLUDED.stock_free,
      asof_date   = EXCLUDED.asof_date,
      updated_at  = now();  -- ← ВАЖНО: обновляем timestamp
END
$$;
