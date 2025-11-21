-- =====================================================================
-- Wine Assistant — полная схема БД (инициализация контейнера)
-- =====================================================================

-- Расширения
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- для gen_random_uuid() и будущих UUID по умолчанию

-- =========================
-- Таблица products
-- =========================
CREATE TABLE IF NOT EXISTS public.products (
  code             TEXT PRIMARY KEY,
  producer         TEXT,
  title_ru         TEXT,
  title_en         TEXT,
  country          TEXT,
  region           TEXT,
  color            TEXT,
  style            TEXT,
  grapes           TEXT,
  abv              TEXT,
  pack             TEXT,
  volume           TEXT,
  -- текущие цены из прайса/файла
  price_rub        NUMERIC,
  price_list_rub   NUMERIC,
  price_final_rub  NUMERIC,
  -- агрегированное поле для поиска
  search_text      TEXT GENERATED ALWAYS AS
    (coalesce(producer,'')||' '||coalesce(title_ru,'')||' '||
     coalesce(country,'')||' '||coalesce(region,'')||' '||
     coalesce(color,'')||' '||coalesce(style,'')||' '||
     coalesce(grapes,'')) STORED,
  -- эмбеддинги (если нужны)
  embedding        VECTOR(1536)
);

-- =========================
-- История цен
-- =========================
CREATE TABLE IF NOT EXISTS public.product_prices (
  id              BIGSERIAL PRIMARY KEY,
  code            TEXT NOT NULL REFERENCES public.products(code) ON DELETE CASCADE,
  price_rub       NUMERIC NOT NULL,
  effective_from  TIMESTAMP WITHOUT TIME ZONE NOT NULL,
  effective_to    TIMESTAMP WITHOUT TIME ZONE
);

-- =========================
-- Текущие остатки
-- =========================
CREATE TABLE IF NOT EXISTS public.inventory (
  code         TEXT PRIMARY KEY REFERENCES public.products(code) ON DELETE CASCADE,
  stock_total  NUMERIC,
  reserved     NUMERIC,
  stock_free   NUMERIC,
  asof_date    DATE,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================
-- История остатков
-- =========================
CREATE TABLE IF NOT EXISTS public.inventory_history (
  id           BIGSERIAL PRIMARY KEY,
  code         TEXT NOT NULL REFERENCES public.products(code) ON DELETE CASCADE,
  stock_total  NUMERIC,
  reserved     NUMERIC,
  stock_free   NUMERIC,
  as_of        TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

-- =====================================================================
-- Индексы (включая те, что проверяет /ready)
-- =====================================================================

-- Может дублировать PK, но нужен именной индекс для readiness
CREATE INDEX IF NOT EXISTS products_code_idx ON public.products (code);

-- Триграммы для быстрого ILIKE/поиска
CREATE INDEX IF NOT EXISTS products_search_idx
  ON public.products USING gin (search_text gin_trgm_ops);

-- Векторный поиск (если используются эмбеддинги)
CREATE INDEX IF NOT EXISTS idx_products_vec
  ON public.products USING ivfflat (embedding vector_l2_ops) WITH (lists=100);

-- История цен: выборки по SKU и дате (имя — как в readiness-check)
CREATE INDEX IF NOT EXISTS product_prices_sku_effective_from_idx
  ON public.product_prices (code, effective_from DESC);

-- Дополнительно — уникальность "срезов" в истории
CREATE UNIQUE INDEX IF NOT EXISTS ux_product_prices_code_from
  ON public.product_prices (code, effective_from);

-- История остатков
CREATE INDEX IF NOT EXISTS idx_inventory_history_code_time
  ON public.inventory_history(code, as_of DESC);

-- Поиск товаров с положительным остатком
CREATE INDEX IF NOT EXISTS idx_inventory_code_free
  ON public.inventory(code, stock_free);

-- =====================================================================
-- Функции
-- =====================================================================

-- Upsert цены в историю (timestamp without time zone)
CREATE OR REPLACE FUNCTION public.upsert_price(
  p_code text,
  p_price numeric,
  p_effective_from timestamp without time zone
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_cur record;
BEGIN
  IF p_price IS NULL THEN
    RETURN;
  END IF;

  SELECT code, price_rub, effective_from
    INTO v_cur
    FROM public.product_prices
   WHERE code = p_code AND effective_to IS NULL
   ORDER BY effective_from DESC
   LIMIT 1;

  IF NOT FOUND THEN
    INSERT INTO public.product_prices(code, price_rub, effective_from, effective_to)
    VALUES (p_code, p_price, p_effective_from, NULL);
    RETURN;
  END IF;

  IF v_cur.price_rub = p_price THEN
    RETURN;
  END IF;

  UPDATE public.product_prices
     SET effective_to = p_effective_from
   WHERE code = p_code AND effective_to IS NULL;

  INSERT INTO public.product_prices(code, price_rub, effective_from, effective_to)
  VALUES (p_code, p_price, p_effective_from, NULL);
END
$$;

-- Перегрузка для timestamptz
CREATE OR REPLACE FUNCTION public.upsert_price(
  p_code text,
  p_price numeric,
  p_effective_from timestamptz
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  PERFORM public.upsert_price(p_code, p_price, p_effective_from::timestamp);
END
$$;

-- Upsert остатков (в историю и текущее состояние)
CREATE OR REPLACE FUNCTION public.upsert_inventory(
  p_code text,
  p_stock_total numeric,
  p_reserved numeric,
  p_stock_free numeric,
  p_as_of timestamp without time zone
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO public.inventory_history(code, stock_total, reserved, stock_free, as_of)
  VALUES (p_code, p_stock_total, p_reserved, p_stock_free, p_as_of);

  INSERT INTO public.inventory(code, stock_total, reserved, stock_free, asof_date)
  VALUES (p_code, p_stock_total, p_reserved, p_stock_free, p_as_of::date)
  ON CONFLICT (code) DO UPDATE
  SET stock_total = EXCLUDED.stock_total,
      reserved    = EXCLUDED.reserved,
      stock_free  = EXCLUDED.stock_free,
      asof_date   = EXCLUDED.asof_date,
      updated_at  = now();
END
$$;
