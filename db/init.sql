CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS products (
  code        TEXT PRIMARY KEY,
  producer    TEXT,
  title_ru    TEXT,
  title_en    TEXT,
  country     TEXT,
  region      TEXT,
  color       TEXT,
  style       TEXT,
  grapes      TEXT,
  abv         TEXT,
  pack        TEXT,
  volume      TEXT,
  price_rub   NUMERIC,
  search_text TEXT GENERATED ALWAYS AS
    (coalesce(producer,'')||' '||coalesce(title_ru,'')||' '||
     coalesce(country,'')||' '||coalesce(region,'')||' '||
     coalesce(color,'')||' '||coalesce(style,'')||' '||
     coalesce(grapes,'')) STORED,
  embedding   VECTOR(1536)
);

CREATE TABLE IF NOT EXISTS product_prices (
  code TEXT REFERENCES products(code) ON DELETE CASCADE,
  price_rub NUMERIC NOT NULL,
  effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
  effective_to   TIMESTAMPTZ,
  PRIMARY KEY (code, effective_from)
);

CREATE TABLE IF NOT EXISTS inventory (
  code TEXT PRIMARY KEY REFERENCES products(code) ON DELETE CASCADE,
  qty  NUMERIC,
  in_stock BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_fts   ON products USING gin (search_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_price ON products (price_rub);
CREATE INDEX IF NOT EXISTS idx_products_vec   ON products USING ivfflat (embedding vector_l2_ops) WITH (lists=100);
