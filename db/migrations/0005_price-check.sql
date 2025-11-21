DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
      FROM pg_constraint
     WHERE conname = 'chk_product_prices_nonneg'
       AND conrelid = 'product_prices'::regclass
  ) THEN
    ALTER TABLE product_prices
      ADD CONSTRAINT chk_product_prices_nonneg
      CHECK (price_rub >= 0);
  END IF;
END $$;
