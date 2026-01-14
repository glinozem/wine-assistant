-- =====================================================================
-- Wine Assistant — DB bootstrap schema (BASE ONLY)
--
-- IMPORTANT:
-- - This file exists ONLY to create the base tables that canonical migrations
--   assume exist (project started as "snapshot-first" DB).
-- - Do NOT add incremental changes here (indexes, constraints, new tables,
--   column changes). Add a new canonical migration instead:
--     db/migrations/NNNN_*.sql
-- =====================================================================

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

  -- legacy/current price (canonical columns are managed by migrations)
  price_rub        NUMERIC,

  -- aggregated field for trigram search; index is created in migrations
  search_text      TEXT GENERATED ALWAYS AS
    (coalesce(producer,'')||' '||coalesce(title_ru,'')||' '||
     coalesce(country,'')||' '||coalesce(region,'')||' '||
     coalesce(color,'')||' '||coalesce(style,'')||' '||
     coalesce(grapes,'')) STORED
);

CREATE TABLE IF NOT EXISTS public.inventory (
  code         TEXT PRIMARY KEY REFERENCES public.products(code) ON DELETE CASCADE,
  stock_total  NUMERIC,
  reserved     NUMERIC,
  stock_free   NUMERIC,
  asof_date    DATE
);
