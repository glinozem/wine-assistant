# Issue #85: Партиционирование `product_prices` и Retention Job

Этот файл — краткая dev-заметка по тому, **как реализовано партиционирование истории цен** и **как работает retention job** для очистки старых данных.

---

## 1. Партиционирование `product_prices`

### 1.1. Общая идея

Проблема: таблица `product_prices` растёт без ограничений (история цен за все годы), что приводит к:

- росту объёма данных и индексов;
- деградации производительности запросов (особенно по конкретному SKU);
- удорожанию хранения и бэкапов.

Решение: перевести таблицу `product_prices` на **партиционирование по дате начала действия цены (`effective_from`)** с шагом в квартал.

### 1.2. Целевая структура

Родительская таблица:

```sql
\d+ product_prices
```

Ключевые моменты:

- Тип: `Partitioned table "public.product_prices"`
- Partition key: `RANGE (effective_from)`
- Основные индексы:
  - `product_prices_partitioned_pkey (id, effective_from)`
  - `idx_product_prices_part_code_from (code, effective_from DESC)`
  - `idx_product_prices_part_open (code) WHERE effective_to IS NULL`
- Ограничения:
  - `chk_product_prices_nonneg` / `product_prices_partitioned_price_rub_check` — цена не отрицательная;
  - FK на `products(code)` с `ON DELETE CASCADE`.

Дочерние партиции (пример):

- `product_prices_2024_q1` — `2024-01-01` → `2024-04-01`
- `product_prices_2024_q2` — `2024-04-01` → `2024-07-01`
- `product_prices_2024_q3` — `2024-07-01` → `2024-10-01`
- `product_prices_2024_q4` — `2024-10-01` → `2025-01-01`
- `product_prices_2025_q1..q4`
- `product_prices_2026_q1` (запас на будущее)

### 1.3. Как это влияет на запросы

Приложенческий SQL **не меняется**: запросы по-прежнему ходят в `product_prices`.
Оптимизация достигается за счёт **partition pruning** на уровне PostgreSQL:

- запросы за последний квартал сканируют 1–2 партиции вместо всей таблицы;
- индексы меньше и лучше ложатся в память;
- исторические данные (старые партиции) можно архивировать/удалять целиком.

Проверка через `EXPLAIN` (пример):

```sql
EXPLAIN ANALYZE
SELECT code, price_rub, effective_from
FROM product_prices
WHERE effective_from >= '2025-10-01'
LIMIT 1000;
```

В плане должно быть видно, что сканируются только нужные партиции (`product_prices_2025_q4`, максимум ещё одна).

---

## 2. Идемпотентная миграция `0011_product_prices_partitioning.sql`

### 2.1. Зачем нужна идемпотентность

Изначально миграция `0011_product_prices_partitioning.sql` была рассчитана на **однократный запуск** поверх «старой» таблицы `product_prices` и содержала прямые `CREATE TABLE product_prices_2024_q1 ...` и т.п.

После первого успешного прогона повторный запуск `migrator` приводил к ошибке:

```text
ERROR:  relation "product_prices_2024_q1" already exists
```

Это ломало сценарии:

- повторный `docker compose up migrator` на dev-окружении;
- развёртывание на окружениях, где миграции могут прогоняться повторно.

### 2.2. Как это реализовано сейчас

Миграция `0011` переписана в **идемпотентном формате**:

- Вся логика завернута в блок `DO $$ ... $$ LANGUAGE plpgsql`.
- В начале выполняется проверка: уже ли `product_prices` партиционирована?

Примерно так (упрощённо):

```sql
DO $$
DECLARE
    is_partitioned boolean;
BEGIN
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

    -- здесь остаётся оригинальное тело миграции:
    -- * создание product_prices_partitioned PARTITION BY RANGE(effective_from)
    -- * создание квартальных партиций
    -- * индексы
    -- * перенос данных и переименование
END;
$$ LANGUAGE plpgsql;
```

Поведение:

- **Новая БД** (ещё не партиционирована): выполняется полное тело миграции.
- **Уже мигрированная БД**: миграция выводит NOTICE и просто завершается (без ошибок).

### 2.3. Проверка

Типичный сценарий проверки:

```bash
docker compose up -d db
docker compose up migrator
```

В логах мигратора для `0011` ожидаем:

```text
[migrator] -> /migrations/migrations/0011_product_prices_partitioning.sql
NOTICE:  0011_product_prices_partitioning: product_prices is already partitioned, skipping migration body
[migrator]    recorded 0011_product_prices_partitioning.sql (...)
```

Плюс прогон `make check` (ruff + pytest), чтобы убедиться, что приложение в целом работает корректно.

---

## 3. Retention job: очистка старых партиций

### 3.1. Зачем нужен retention

Основная идея: **хранить историю цен ограниченное время** (например, последние 2 года), а более старые данные удалять целыми партициями, чтобы таблица и индексы не росли бесконечно.

Преимущества:

- контролируемый размер БД;
- предсказуемая производительность;
- более быстрые бэкапы и восстановление.

### 3.2. Скрипт `jobs/cleanup_old_partitions.py`

Скрипт отвечает за поиск и удаление «устаревших» партиций `product_prices_*`.

Ключевые параметры:

- `RETENTION_DAYS` — целевой период хранения (по умолчанию 730 дней ≈ 2 года);
- `DRY_RUN` — режим «только посмотреть», без реального удаления.

Основные шаги внутри скрипта:

1. Рассчитать граничную дату:

   ```python
   retention_date = datetime.now() - timedelta(days=RETENTION_DAYS)
   ```

2. Получить список партиций `product_prices` из каталога PostgreSQL:

   ```sql
   SELECT
       child.relname AS partition_name,
       pg_get_expr(child.relpartbound, child.oid) AS partition_range
   FROM pg_inherits
   JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
   JOIN pg_class child ON pg_inherits.inhrelid = child.oid
   WHERE parent.relname = 'product_prices'
   ORDER BY child.relname;
   ```

3. Отфильтровать «старые» партиции по имени/годам (`product_prices_YYYY_qN`) относительно `retention_date`.

4. Для каждой партиции:

   - посчитать её размер через `pg_total_relation_size`;
   - в логах вывести имя и размер;
   - если `DRY_RUN = true` → только логировать, без изменений;
   - если `DRY_RUN = false`:
     - `ALTER TABLE product_prices DETACH PARTITION <partition_name>;`
     - `DROP TABLE <partition_name>;`

### 3.3. Как запускать

Локальный тестовый запуск (DRY RUN):

```bash
DRY_RUN=true python jobs/cleanup_old_partitions.py
```

Ожидаем в логах список партиций, которые **были бы** удалены.

Боевой запуск (по умолчанию 2 года хранения):

```bash
DRY_RUN=false RETENTION_DAYS=730 python jobs/cleanup_old_partitions.py
```

В проде скрипт может запускаться по cron, например раз в месяц:

```cron
# 1-го числа каждого месяца в 03:00
0 3 1 * * cd /app && /app/.venv/bin/python /app/jobs/cleanup_old_partitions.py >> /var/log/retention_policy.log 2>&1
```

---

## 4. Мини-чеки для себя/ревьюера

- [ ] `\d+ product_prices` показывает partitioned table с квартальными партициями.
- [ ] `docker compose up migrator` отрабатывает без ошибок, `0011` пишет NOTICE и пропускает тело при повторном запуске.
- [ ] `make check` зелёный.
- [ ] `DRY_RUN=true python jobs/cleanup_old_partitions.py` корректно выводит список старых партиций (если они есть).
- [ ] В проде согласована целевая retention-политика (`RETENTION_DAYS`) и расписание запуска job’а.
