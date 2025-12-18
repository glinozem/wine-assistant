BEGIN;

-- 0) Чтобы больше никогда не было коллизий “по имени”:
--    переименуем исторический constraint на product_prices_old (если есть).
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_constraint c
    WHERE c.conname = 'product_prices_no_overlap'
      AND c.conrelid = 'public.product_prices_old'::regclass
  ) THEN
    ALTER TABLE public.product_prices_old
      RENAME CONSTRAINT product_prices_no_overlap TO product_prices_old_no_overlap;
  END IF;
END $$;

-- 1) Индекс для быстрых проверок по code + effective_from (partitioned index)
CREATE INDEX IF NOT EXISTS ix_product_prices_code_from
  ON public.product_prices (code, effective_from);

-- 2) Sanity-check интервала
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_product_prices_valid_range'
      AND conrelid = 'public.product_prices'::regclass
  ) THEN
    ALTER TABLE public.product_prices
      ADD CONSTRAINT chk_product_prices_valid_range
      CHECK (effective_to IS NULL OR effective_to > effective_from) NOT VALID;

    ALTER TABLE public.product_prices
      VALIDATE CONSTRAINT chk_product_prices_valid_range;
  END IF;
END $$;

-- 3) Функция проверки “нет пересечений” (проверяем только ближайших соседей по времени)
CREATE OR REPLACE FUNCTION public.product_prices_assert_no_overlap()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  new_to timestamp;
  prev_to timestamp;
  prev_from timestamp;
  prev_id bigint;

  next_from timestamp;
  next_id bigint;
BEGIN
  new_to := COALESCE(NEW.effective_to, 'infinity'::timestamp);

  IF new_to <= NEW.effective_from THEN
    RAISE EXCEPTION 'product_prices invalid interval for code=%: [% .. %)',
      NEW.code, NEW.effective_from, NEW.effective_to;
  END IF;

  -- prev row: ближайшая запись слева (максимальный effective_from < new_to)
  SELECT p.id, p.effective_from, COALESCE(p.effective_to, 'infinity'::timestamp)
    INTO prev_id, prev_from, prev_to
  FROM public.product_prices p
  WHERE p.code = NEW.code
    AND p.id <> NEW.id
    AND p.effective_from < new_to
  ORDER BY p.effective_from DESC
  LIMIT 1;

  IF prev_id IS NOT NULL AND prev_to > NEW.effective_from THEN
    RAISE EXCEPTION 'product_prices overlap (prev) for code=% around [% .. %)',
      NEW.code, NEW.effective_from, NEW.effective_to;
  END IF;

  -- next row: ближайшая запись справа (минимальный effective_from >= new_from)
  SELECT p.id, p.effective_from
    INTO next_id, next_from
  FROM public.product_prices p
  WHERE p.code = NEW.code
    AND p.id <> NEW.id
    AND p.effective_from >= NEW.effective_from
  ORDER BY p.effective_from ASC
  LIMIT 1;

  IF next_id IS NOT NULL AND next_from < new_to THEN
    RAISE EXCEPTION 'product_prices overlap (next) for code=% around [% .. %)',
      NEW.code, NEW.effective_from, NEW.effective_to;
  END IF;

  RETURN NEW;
END $$;

-- 4) Constraint trigger: DEFERRABLE INITIALLY DEFERRED (как было у EXCLUDE)
--    Чтобы ETL мог “сначала закрыть старую запись, потом вставить новую”
--    или наоборот — проверка будет на COMMIT.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgname = 'trg_product_prices_no_overlap'
      AND tgrelid = 'public.product_prices'::regclass
      AND NOT tgisinternal
  ) THEN
    CREATE CONSTRAINT TRIGGER trg_product_prices_no_overlap
      AFTER INSERT OR UPDATE OF code, effective_from, effective_to
      ON public.product_prices
      DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW
      EXECUTE FUNCTION public.product_prices_assert_no_overlap();
  END IF;
END $$;

COMMIT;
