\pset pager off
\echo === Diagnostics: product_prices & inventory_history ===

SELECT to_regclass('public.ux_product_prices_code_from') AS ux_idx_product_prices_code_from;

SELECT conname AS price_check_nonneg
  FROM pg_constraint
 WHERE conname='chk_product_prices_nonneg';

SELECT conname AS overlap_guard
  FROM pg_constraint
 WHERE conname='product_prices_no_overlap';

SELECT pg_get_indexdef(i.indexrelid) AS indexdef
  FROM pg_index i
  JOIN pg_class c ON c.oid = i.indexrelid
 WHERE c.relname='ux_product_prices_code_from';

\echo -- Sanity: перекрытия интервалов не допускаются, ожидаем 0
WITH pairs AS (
  SELECT p1.code,
         tstzrange(p1.effective_from::timestamptz, COALESCE(p1.effective_to,'infinity')::timestamptz, '[)') AS r1,
         tstzrange(p2.effective_from::timestamptz, COALESCE(p2.effective_to,'infinity')::timestamptz, '[)') AS r2
    FROM product_prices p1
    JOIN product_prices p2
      ON p2.code=p1.code AND p2.ctid<>p1.ctid
   WHERE tstzrange(p1.effective_from::timestamptz, COALESCE(p1.effective_to,'infinity')::timestamptz, '[)')
         && tstzrange(p2.effective_from::timestamptz, COALESCE(p2.effective_to,'infinity')::timestamptz, '[)')
)
SELECT COUNT(*) AS overlaps FROM pairs;

\echo -- Negative prices (ожидаем 0)
SELECT COUNT(*) AS negatives FROM product_prices WHERE price_rub < 0;

\echo -- inventory_history: индекс по (code, as_of desc)
SELECT to_regclass('public.idx_inventory_history_code_time') AS idx_inventory_history_code_time;

\echo -- Несогласованные значения свободного остатка (ожидаем 0)
SELECT COUNT(*) AS free_mismatch
  FROM inventory_history
 WHERE stock_free IS NOT NULL
   AND stock_total IS NOT NULL
   AND reserved IS NOT NULL
   AND stock_free <> (stock_total - reserved);
