-- tests/fixtures/schema_prices.sql
-- Product catalog schema used in tests (separated to keep CI steps modular).

\set ON_ERROR_STOP on
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.products (
  code              text PRIMARY KEY,
  producer          text,
  title_ru          text,
  title_en          text,
  country           text,
  region            text,
  grapes            text,
  abv               numeric(5,2),
  pack              int,
  volume            numeric(6,3),
  price_list_rub    numeric(12,2),
  price_final_rub   numeric(12,2),
  price_rub         numeric(12,2),
  search_text       text GENERATED ALWAYS AS (
    lower(
      coalesce(title_ru,'') || ' ' ||
      coalesce(title_en,'') || ' ' ||
      coalesce(producer,'') || ' ' ||
      coalesce(country,'') || ' ' ||
      coalesce(region,'') || ' ' ||
      coalesce(grapes,'')
    )
  ) STORED
);

CREATE TABLE IF NOT EXISTS public.inventory (
  code        text PRIMARY KEY REFERENCES public.products(code) ON DELETE CASCADE,
  stock_total int,
  reserved    int,
  stock_free  int,
  asof_date   timestamptz
);

CREATE TABLE IF NOT EXISTS public.product_prices (
  id               bigserial PRIMARY KEY,
  code             text NOT NULL REFERENCES public.products(code) ON DELETE CASCADE,
  price            numeric(12,2) NOT NULL,
  price_list_rub   numeric(12,2),
  price_final_rub  numeric(12,2),
  effective_from   date NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now()
);

-- Indexes required by readiness checks and tests
CREATE INDEX IF NOT EXISTS products_code_idx ON public.products (code);
CREATE INDEX IF NOT EXISTS products_search_idx ON public.products USING gin (search_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS product_prices_sku_effective_from_idx ON public.product_prices (code, effective_from DESC);
