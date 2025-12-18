-- Guardrails for product_prices: уникальность, неотрицательная цена, отсутствие перекрытий, нормализация effective_to

-- расширение под EXCLUDE
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- уникальный индекс на (code, effective_from)
CREATE UNIQUE INDEX IF NOT EXISTS ux_product_prices_code_from
  ON product_prices(code, effective_from);

-- check: цены неотрицательные (на случай если отдельная миграция ещё не ставилась)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_product_prices_nonneg'
  ) THEN
    ALTER TABLE product_prices
      ADD CONSTRAINT chk_product_prices_nonneg
      CHECK (price_rub >= 0) NOT VALID;
    ALTER TABLE product_prices VALIDATE CONSTRAINT chk_product_prices_nonneg;
  END IF;
END $$;

-- нормализация: effective_to = следующий effective_from (по code), если не совпадает/пусто/инверсия
WITH ordered AS (
  SELECT ctid, code, effective_from,
         LEAD(effective_from) OVER (PARTITION BY code ORDER BY effective_from) AS next_from
    FROM product_prices
)
UPDATE product_prices p
   SET effective_to = o.next_from
  FROM ordered o
 WHERE p.ctid = o.ctid
   AND (
         p.effective_to IS NULL
      OR (o.next_from IS NOT NULL AND p.effective_to <> o.next_from)
      OR p.effective_to < p.effective_from
   );

-- запрет перекрывающихся интервалов (DEFERRABLE — удобно для батчей)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname='product_prices_no_overlap'
  ) THEN
    ALTER TABLE product_prices
      ADD CONSTRAINT product_prices_no_overlap
      EXCLUDE USING gist (
        code WITH =,
        tstzrange(
          effective_from::timestamptz,
          COALESCE(effective_to, 'infinity')::timestamptz,
          '[)'
        ) WITH &&
      )
      DEFERRABLE INITIALLY DEFERRED;
  END IF;
END $$;
