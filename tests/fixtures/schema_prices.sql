-- products / inventory (+ price_history про запас)
CREATE TABLE IF NOT EXISTS public.products (
  code TEXT PRIMARY KEY,
  producer TEXT,
  title_ru TEXT,
  country TEXT,
  region TEXT,
  grapes TEXT,
  abv NUMERIC,
  pack INTEGER,
  volume NUMERIC,
  price_list_rub NUMERIC,
  price_final_rub NUMERIC,
  price_rub NUMERIC
);

CREATE TABLE IF NOT EXISTS public.inventory (
  code TEXT PRIMARY KEY,
  stock_total INTEGER,
  reserved INTEGER,
  stock_free INTEGER,
  asof_date TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.price_history (
  id BIGSERIAL PRIMARY KEY,
  code TEXT NOT NULL,
  asof_date TIMESTAMP NOT NULL,
  price NUMERIC,
  envelope_id UUID
);
