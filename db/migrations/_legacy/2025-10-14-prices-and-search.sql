-- =====================================================================
-- Prices & Search migration (products: two prices; price history; stock history)
-- =====================================================================

-- Расширения (безопасно, IF NOT EXISTS)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

-- Две цены в products: прайс и финальная
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_list_rub  numeric;
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_final_rub numeric;

-- Бэкофил: если новые колонки пустые, возьми старое price_rub
UPDATE products SET price_list_rub  = COALESCE(price_list_rub,  price_rub) WHERE price_rub IS NOT NULL;
UPDATE products SET price_final_rub = COALESCE(price_final_rub, price_rub) WHERE price_rub IS NOT NULL;

-- Индексы для ускорения фильтров по цене
CREATE INDEX IF NOT EXISTS idx_products_price_list_rub  ON products(price_list_rub);
CREATE INDEX IF NOT EXISTS idx_products_price_final_rub ON products(price_final_rub);

-- Страховка: GIN по search_text (если не был создан)
CREATE INDEX IF NOT EXISTS idx_products_search_text_gin ON products USING gin (search_text gin_trgm_ops);

-- История цен (если таблицы нет)
CREATE TABLE IF NOT EXISTS product_prices (
  id             bigserial PRIMARY KEY,
  code           text NOT NULL REFERENCES products(code) ON DELETE CASCADE,
  price_rub      numeric NOT NULL,
  effective_from timestamp without time zone NOT NULL,
  effective_to   timestamp without time zone
);

-- Индексы по истории цен
CREATE INDEX IF NOT EXISTS idx_product_prices_open      ON product_prices(code) WHERE effective_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_product_prices_code_from ON product_prices(code, effective_from DESC);

DROP FUNCTION IF EXISTS upsert_price(text, numeric, timestamptz);

-- Функция upsert_price (timestamp without time zone)
CREATE OR REPLACE FUNCTION upsert_price(
  p_code text,
  p_price numeric,
  p_effective_from timestamp without time zone
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  v_cur record;
BEGIN
  IF p_price IS NULL THEN
    RETURN;
  END IF;

  SELECT code, price_rub, effective_from
  INTO v_cur
  FROM product_prices
  WHERE code = p_code AND effective_to IS NULL
  ORDER BY effective_from DESC
  LIMIT 1;

  IF NOT FOUND THEN
    INSERT INTO product_prices(code, price_rub, effective_from, effective_to)
    VALUES (p_code, p_price, p_effective_from, NULL);
    RETURN;
  END IF;

  -- Если цена не изменилась — ничего не делаем
  IF v_cur.price_rub = p_price THEN
    RETURN;
  END IF;

  -- Закрываем прошлую цену на момент новой
  UPDATE product_prices
  SET effective_to = p_effective_from
  WHERE code = p_code AND effective_to IS NULL;

  -- Открываем новую цену
  INSERT INTO product_prices(code, price_rub, effective_from, effective_to)
  VALUES (p_code, p_price, p_effective_from, NULL);
END
$$;

-- Перегрузка под timestamptz (делегирует в вариант без таймзоны)
CREATE OR REPLACE FUNCTION upsert_price(
  p_code text,
  p_price numeric,
  p_effective_from timestamptz
) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  PERFORM upsert_price(p_code, p_price, p_effective_from::timestamp);
END
$$;

-- Таблица истории остатков (для аналитики/прогнозов)
CREATE TABLE IF NOT EXISTS inventory_history (
  id          bigserial PRIMARY KEY,
  code        text NOT NULL REFERENCES products(code) ON DELETE CASCADE,
  stock_total numeric,
  reserved    numeric,
  stock_free  numeric,
  as_of       timestamp without time zone NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inventory_history_code_time ON inventory_history(code, as_of DESC);

-- Удобная функция: апсерт текущих остатков + запись в историю
CREATE OR REPLACE FUNCTION upsert_inventory(
  p_code text,
  p_stock_total numeric,
  p_reserved numeric,
  p_stock_free numeric,
  p_as_of timestamp without time zone
) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO inventory_history(code, stock_total, reserved, stock_free, as_of)
  VALUES (p_code, p_stock_total, p_reserved, p_stock_free, p_as_of);

  INSERT INTO inventory(code, stock_total, reserved, stock_free)
  VALUES (p_code, p_stock_total, p_reserved, p_stock_free)
  ON CONFLICT (code) DO UPDATE
  SET stock_total = EXCLUDED.stock_total,
      reserved    = EXCLUDED.reserved,
      stock_free  = EXCLUDED.stock_free;
END
$$;

-- Индекс на текущие остатки
CREATE INDEX IF NOT EXISTS idx_inventory_code_free ON inventory(code, stock_free);
