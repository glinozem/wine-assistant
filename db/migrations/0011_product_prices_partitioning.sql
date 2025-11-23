-- 0011_product_prices_partitioning.sql
--
-- Партиционирование таблицы product_prices по кварталам + подготовка к retention policy.
--
-- Допущения:
--   - Существует таблица product_prices со следующими полями (минимальный набор):
--       id            BIGSERIAL PRIMARY KEY
--       code          TEXT NOT NULL REFERENCES products(code)
--       price_rub     NUMERIC NOT NULL CHECK (price_rub >= 0)
--       effective_from TIMESTAMP WITHOUT TIME ZONE NOT NULL
--       effective_to   TIMESTAMP WITHOUT TIME ZONE
--   - business-логика и функции (upsert_price и т.п.) обращаются к таблице под именем product_prices
--     и не завязаны на конкретный тип хранения (обычная / партиционированная).
--
-- Цель:
--   - Перевести product_prices на декларативное партиционирование по RANGE (effective_from)
--     с квартальными партициями.
--   - Сохранить все существующие данные.
--   - Оставить название таблицы product_prices для обратной совместимости.
--
-- ВАЖНО: миграция предполагает окно обслуживания, т.к. на время INSERT ... SELECT возможны блокировки.
--        Желательно выполнять во время простоя импорта / API.

BEGIN;

-- ---------------------------------------------------------------------
-- Шаг 1. Создаём новую партиционированную таблицу с той же схемой.
-- ---------------------------------------------------------------------

CREATE TABLE product_prices_partitioned (
    id BIGSERIAL,
    code TEXT NOT NULL,
    price_rub NUMERIC NOT NULL CHECK (price_rub >= 0),
    effective_from TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    effective_to TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (id, effective_from),       -- ключ включает partition key
    FOREIGN KEY (code) REFERENCES products(code) ON DELETE CASCADE
) PARTITION BY RANGE (effective_from);

-- ---------------------------------------------------------------------
-- Шаг 2. Создаём квартальные партиции для 2024–2026 годов.
-- При необходимости добавить более ранние/поздние периоды отдельной миграцией.
-- ---------------------------------------------------------------------

-- 2024
CREATE TABLE product_prices_2024_q1 PARTITION OF product_prices_partitioned
  FOR VALUES FROM ('2024-01-01') TO ('2024-04-01');

CREATE TABLE product_prices_2024_q2 PARTITION OF product_prices_partitioned
  FOR VALUES FROM ('2024-04-01') TO ('2024-07-01');

CREATE TABLE product_prices_2024_q3 PARTITION OF product_prices_partitioned
  FOR VALUES FROM ('2024-07-01') TO ('2024-10-01');

CREATE TABLE product_prices_2024_q4 PARTITION OF product_prices_partitioned
  FOR VALUES FROM ('2024-10-01') TO ('2025-01-01');

-- 2025
CREATE TABLE product_prices_2025_q1 PARTITION OF product_prices_partitioned
  FOR VALUES FROM ('2025-01-01') TO ('2025-04-01');

CREATE TABLE product_prices_2025_q2 PARTITION OF product_prices_partitioned
  FOR VALUES FROM ('2025-04-01') TO ('2025-07-01');

CREATE TABLE product_prices_2025_q3 PARTITION OF product_prices_partitioned
  FOR VALUES FROM ('2025-07-01') TO ('2025-10-01');

CREATE TABLE product_prices_2025_q4 PARTITION OF product_prices_partitioned
  FOR VALUES FROM ('2025-10-01') TO ('2026-01-01');

-- 2026 (задел на будущее)
CREATE TABLE product_prices_2026_q1 PARTITION OF product_prices_partitioned
  FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');

-- При необходимости можно добавить DEFAULT-партицию для неожиданных дат.
-- CREATE TABLE product_prices_default PARTITION OF product_prices_partitioned DEFAULT;

-- ---------------------------------------------------------------------
-- Шаг 3. Индексы (создаются на родительской таблице — Postgres создаст их на всех партициях).
-- ---------------------------------------------------------------------

CREATE INDEX idx_product_prices_part_code_from
    ON product_prices_partitioned (code, effective_from DESC);

CREATE INDEX idx_product_prices_part_open
    ON product_prices_partitioned (code)
    WHERE effective_to IS NULL;

-- ---------------------------------------------------------------------
-- Шаг 4. Перенос данных из старой таблицы.
-- ---------------------------------------------------------------------

INSERT INTO product_prices_partitioned (id, code, price_rub, effective_from, effective_to)
SELECT id, code, price_rub, effective_from, effective_to
FROM product_prices;

-- ---------------------------------------------------------------------
-- Шаг 5. Обновляем sequence для нового id.
-- ---------------------------------------------------------------------

-- Важно: на этом этапе product_prices_partitioned уже содержит все строки.
SELECT setval('product_prices_partitioned_id_seq',
              (SELECT COALESCE(MAX(id), 1) FROM product_prices_partitioned));

-- ---------------------------------------------------------------------
-- Шаг 6. Переименовываем таблицы.
-- ---------------------------------------------------------------------

ALTER TABLE product_prices RENAME TO product_prices_old;
ALTER TABLE product_prices_partitioned RENAME TO product_prices;

-- Опционально можно переименовать sequence, чтобы имя было привычным:
-- ALTER SEQUENCE product_prices_partitioned_id_seq RENAME TO product_prices_id_seq;

-- ---------------------------------------------------------------------
-- Шаг 7. (опционально) Удалить старую таблицу после успешного деплоя и проверки.
-- На первом этапе оставляем её для возможности отката.
-- ---------------------------------------------------------------------
-- DROP TABLE product_prices_old;

-- ---------------------------------------------------------------------
-- Шаг 8. Функция автоматического создания квартальных партиций.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION create_quarterly_partitions(
    start_date DATE,
    num_quarters INT DEFAULT 4
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    quarter_start DATE;
    quarter_end   DATE;
    partition_name TEXT;
    year_part TEXT;
    quarter_num INT;
BEGIN
    FOR i IN 0..(num_quarters - 1) LOOP
        quarter_start := start_date + (i * INTERVAL '3 months');
        quarter_end   := quarter_start + INTERVAL '3 months';

        year_part   := TO_CHAR(quarter_start, 'YYYY');
        quarter_num := EXTRACT(QUARTER FROM quarter_start);

        partition_name := 'product_prices_' || year_part || '_q' || quarter_num;

        -- Проверяем, что партиция с таким именем ещё не существует
        IF NOT EXISTS (
            SELECT 1
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r'
              AND n.nspname = 'public'
              AND c.relname = partition_name
        ) THEN
            EXECUTE format(
                'CREATE TABLE %I PARTITION OF product_prices FOR VALUES FROM (%L) TO (%L)',
                partition_name,
                quarter_start,
                quarter_end
            );
        END IF;
    END LOOP;
END;
$$;

COMMENT ON TABLE product_prices IS 'Партиционированная таблица истории цен по кварталам.';

COMMIT;
