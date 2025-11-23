-- 0011_product_prices_partitioning.sql
-- Партиционирование product_prices по кварталам + миграция данных

DO $$
DECLARE
    is_partitioned boolean;
BEGIN
    -- Проверяем, не является ли product_prices уже партиционированной таблицей
    SELECT EXISTS (
        SELECT 1
        FROM pg_partitioned_table pt
        JOIN pg_class c ON c.oid = pt.partrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'product_prices'
          AND n.nspname = 'public'
    )
    INTO is_partitioned;

    IF is_partitioned THEN
        RAISE NOTICE '0011_product_prices_partitioning: product_prices is already partitioned, skipping migration body';
        RETURN;
    END IF;

    -- 1. Создаём новую партиционированную таблицу
    EXECUTE $stmt$
        CREATE TABLE product_prices_partitioned (
            id BIGSERIAL,
            code TEXT NOT NULL,
            price_rub NUMERIC NOT NULL CHECK (price_rub >= 0),
            effective_from TIMESTAMP NOT NULL,
            effective_to TIMESTAMP,
            PRIMARY KEY (id, effective_from),
            FOREIGN KEY (code) REFERENCES products(code) ON DELETE CASCADE
        ) PARTITION BY RANGE (effective_from)
    $stmt$;

    -- 2. Партиции для 2024–2026 годов

    -- 2024
    EXECUTE $stmt$
        CREATE TABLE product_prices_2024_q1 PARTITION OF product_prices_partitioned
        FOR VALUES FROM ('2024-01-01') TO ('2024-04-01')
    $stmt$;

    EXECUTE $stmt$
        CREATE TABLE product_prices_2024_q2 PARTITION OF product_prices_partitioned
        FOR VALUES FROM ('2024-04-01') TO ('2024-07-01')
    $stmt$;

    EXECUTE $stmt$
        CREATE TABLE product_prices_2024_q3 PARTITION OF product_prices_partitioned
        FOR VALUES FROM ('2024-07-01') TO ('2024-10-01')
    $stmt$;

    EXECUTE $stmt$
        CREATE TABLE product_prices_2024_q4 PARTITION OF product_prices_partitioned
        FOR VALUES FROM ('2024-10-01') TO ('2025-01-01')
    $stmt$;

    -- 2025
    EXECUTE $stmt$
        CREATE TABLE product_prices_2025_q1 PARTITION OF product_prices_partitioned
        FOR VALUES FROM ('2025-01-01') TO ('2025-04-01')
    $stmt$;

    EXECUTE $stmt$
        CREATE TABLE product_prices_2025_q2 PARTITION OF product_prices_partitioned
        FOR VALUES FROM ('2025-04-01') TO ('2025-07-01')
    $stmt$;

    EXECUTE $stmt$
        CREATE TABLE product_prices_2025_q3 PARTITION OF product_prices_partitioned
        FOR VALUES FROM ('2025-07-01') TO ('2025-10-01')
    $stmt$;

    EXECUTE $stmt$
        CREATE TABLE product_prices_2025_q4 PARTITION OF product_prices_partitioned
        FOR VALUES FROM ('2025-10-01') TO ('2026-01-01')
    $stmt$;

    -- 2026 (заранее)
    EXECUTE $stmt$
        CREATE TABLE product_prices_2026_q1 PARTITION OF product_prices_partitioned
        FOR VALUES FROM ('2026-01-01') TO ('2026-04-01')
    $stmt$;

    -- 3. Индексы на партиционированной таблице
    EXECUTE $stmt$
        CREATE INDEX idx_product_prices_part_code_from
            ON product_prices_partitioned (code, effective_from DESC)
    $stmt$;

    EXECUTE $stmt$
        CREATE INDEX idx_product_prices_part_open
            ON product_prices_partitioned (code)
            WHERE effective_to IS NULL
    $stmt$;

    -- 4. Переносим данные
    EXECUTE $stmt$
        INSERT INTO product_prices_partitioned (id, code, price_rub, effective_from, effective_to)
        SELECT id, code, price_rub, effective_from, effective_to
        FROM product_prices
    $stmt$;

    -- 5. Переименовываем таблицы
    EXECUTE $stmt$
        ALTER TABLE product_prices RENAME TO product_prices_old
    $stmt$;

    EXECUTE $stmt$
        ALTER TABLE product_prices_partitioned RENAME TO product_prices
    $stmt$;

    -- 6. Обновляем sequence для id
    EXECUTE $stmt$
        SELECT setval(
            'product_prices_partitioned_id_seq',
            (SELECT COALESCE(MAX(id), 1) FROM product_prices)
        )
    $stmt$;

    -- 7. Комментарий на таблицу
    EXECUTE $stmt$
        COMMENT ON TABLE product_prices IS 'Партиционированная таблица истории цен по кварталам'
    $stmt$;

END $$;
