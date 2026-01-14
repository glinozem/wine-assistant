# Effective ranges remediation (product_prices)

Документ предназначен для устранения проблем с “effective ranges” (интервалами действия цены) в `public.product_prices` и для последующей валидации guardrails.

Этот playbook используется как remediation-процедура к канону миграций и CI-guardrails, см. `docs/dev/db-migrations.md`.

---

## 1) Контекст и текущая модель данных

### Таблица `public.product_prices`

- Хранит историю цен по SKU (`code`) как интервалы:
  - `effective_from TIMESTAMP NOT NULL`
  - `effective_to   TIMESTAMP NULL` (NULL = «открытый» интервал)
- После миграции партиционирования (`0011_product_prices_partitioning.sql`) `public.product_prices` является **партиционированной** таблицей (RANGE по `effective_from`) и существует историческая таблица `public.product_prices_old`.

### Guardrails (инварианты, которые должны выполняться)

В текущих миграциях предусмотрены guardrails:

1) **Валидность границ интервала**
- constraint: `chk_product_prices_valid_range`
- смысл: `effective_to IS NULL OR effective_to > effective_from`

2) **Отсутствие пересечений интервалов для одного code**
- constraint trigger: `trg_product_prices_no_overlap`
- функция: `public.product_prices_assert_no_overlap()`
- смысл: интервалы одного `code` не пересекаются (включая запрет на “две открытые строки” одновременно).

3) **Неотрицательная цена**
- constraint: `chk_product_prices_nonneg`
- смысл: `price_rub >= 0`

---

## 2) Что считаем invalid

Ниже — определения для диагностики и remediation.

### 2.1 Invalid (ошибка, должно стать 0)

1) **Invalid range**
- `effective_to IS NOT NULL AND effective_to <= effective_from`

2) **Overlap (пересечения)**
- для одного `code` существует пара строк, где интервалы пересекаются.
- частный случай: **>1 “open interval”** (несколько строк с `effective_to IS NULL` для одного `code`).

3) **Duplicates by start**
- для одного `code` есть несколько строк с одинаковым `effective_from` (обычно это “двойная вставка” или неполная дедупликация).

### 2.2 Warning (не всегда ошибка)

4) **Gaps (дырки)**
- следующий интервал начинается позже, чем заканчивается предыдущий: `prev.effective_to < next.effective_from`.
- В текущем playbook **не заполняем gaps автоматически**, потому что это меняет фактический смысл данных (неизвестно, какая цена была в промежутке).
- Gaps считаем “warning” и выносим в отчёт для дальнейшего решения (по бизнес-правилам или ретроспективной загрузке данных).

---

## 3) Диагностика (read-only) до remediation

Все запросы ниже выполняются на `public.product_prices` (родительской таблице), PostgreSQL прозрачно читает партиции.

### 3.1 Сводка нарушений (counts)

```sql
-- 1) Invalid ranges
select count(*) as invalid_ranges
from public.product_prices
where effective_to is not null and effective_to <= effective_from;

-- 2) Multiple open intervals (должно быть 0)
select count(*) as codes_with_multiple_open
from (
  select code
  from public.product_prices
  where effective_to is null
  group by code
  having count(*) > 1
) t;

-- 3) Duplicate effective_from per code (должно быть 0)
select count(*) as duplicated_starts
from (
  select code, effective_from
  from public.product_prices
  group by code, effective_from
  having count(*) > 1
) t;
```

### 3.2 Overlap и gaps через window functions (масштабируемо)

```sql
with ordered as (
  select
    id, code, price_rub, effective_from, effective_to,
    lag(effective_from) over (partition by code order by effective_from, id) as prev_from,
    lag(effective_to)   over (partition by code order by effective_from, id) as prev_to,
    lead(effective_from) over (partition by code order by effective_from, id) as next_from
  from public.product_prices
)
select
  -- overlap: предыдущий интервал (prev_to) заходит за текущий start
  count(*) filter (
    where prev_from is not null
      and coalesce(prev_to, 'infinity'::timestamp) > effective_from
  ) as overlaps_via_prev,
  -- gap: предыдущий интервал закончился раньше текущего start (prev_to < effective_from)
  count(*) filter (
    where prev_from is not null
      and prev_to is not null
      and prev_to < effective_from
  ) as gaps
from ordered;
```

### 3.3 Сэмплы нарушений (для отчёта)

```sql
-- показать 50 примеров overlap
with ordered as (
  select
    id, code, price_rub, effective_from, effective_to,
    lag(effective_to) over (partition by code order by effective_from, id) as prev_to
  from public.product_prices
)
select *
from ordered
where prev_to is not null and prev_to > effective_from
order by code, effective_from
limit 50;

-- показать 50 примеров invalid ranges
select *
from public.product_prices
where effective_to is not null and effective_to <= effective_from
order by code, effective_from
limit 50;

-- показать 50 примеров duplicate starts
select pp.*
from public.product_prices pp
join (
  select code, effective_from
  from public.product_prices
  group by code, effective_from
  having count(*) > 1
) d using (code, effective_from)
order by pp.code, pp.effective_from, pp.id desc
limit 50;
```

---

## 4) Подготовка и безопасность

### 4.1 Остановить writers (рекомендуется)

Remediation меняет историю цен и должна выполняться без конкурентных вставок/обновлений (Daily Import / API).

Рекомендуемый вариант (локально/стенд):
- остановить сервис API на время remediation:
  - Docker: `docker compose stop api`
- убедиться, что нет активных import-jobs.

### 4.2 Backup strategy (обязательная)

#### Вариант A: pg_dump (предпочтительный)

```bash
# из хоста (пример; подставьте свои параметры)
pg_dump -Fc -h localhost -p 15432 -U postgres -d wine_db \
  -t public.product_prices -t public.product_prices_old \
  -f backups/product_prices_before_effective_ranges.dump
```

#### Вариант B: backup table (быстро, но “внутри БД”)

```sql
-- Создаёт обычную (непартиционированную) таблицу-слепок
create table if not exists public.product_prices_backup__before_effective_ranges
as
select * from public.product_prices;

-- Рекомендуется сохранить размер/статистику
analyze public.product_prices_backup__before_effective_ranges;
```

---

## 5) Remediation: “готовый к запуску” сценарий (dry-run → apply)

Ниже приведён сценарий, который:
- удаляет дубликаты `(code, effective_from)` (оставляет строку с максимальным `id`);
- исправляет `effective_to`, если:
  - есть overlap (обрезает предыдущий интервал до начала следующего),
  - есть “лишний open interval” (закрывает открытый интервал, если справа есть следующий),
  - есть invalid bounds (переопределяет `effective_to` на безопасное значение).
- **gaps не заполняет** (оставляет `effective_to` как есть, если оно раньше `next_from`).

### 5.1 Dry-run (оценка объёма изменений)

```sql
with base as (
  select
    id, code, price_rub, effective_from, effective_to,
    lead(effective_from) over (partition by code order by effective_from, id) as next_from,
    row_number() over (partition by code, effective_from order by id desc) as rn_same_from
  from public.product_prices
),
plan as (
  select
    id, code, effective_from, effective_to, next_from, rn_same_from,
    case
      when rn_same_from > 1 then null
      when next_from is null then
        case
          when effective_to is null then null
          when effective_to <= effective_from then null
          else effective_to
        end
      else
        case
          when next_from <= effective_from then null
          when effective_to is null then next_from
          when effective_to <= effective_from then next_from
          when effective_to > next_from then next_from
          else effective_to
        end
    end as fixed_to
  from base
)
select
  count(*) filter (where rn_same_from > 1) as to_delete_duplicates,
  count(*) filter (
    where rn_same_from = 1
      and (
        (fixed_to is null and effective_to is not null)
        or (fixed_to is not null and effective_to is null)
        or (fixed_to is not null and effective_to is not null and fixed_to <> effective_to)
      )
  ) as to_update_effective_to
from plan;
```

### 5.2 Apply (transactional)

```sql
begin;

-- Рекомендовано: ограничить время и гарантировать откат в случае ошибок
set local statement_timeout = '10min';
set local lock_timeout = '30s';

-- Блокируем таблицу, чтобы избежать конкурентных изменений
lock table public.product_prices in share row exclusive mode;

-- constraint trigger сделан DEFERRABLE INITIALLY DEFERRED;
-- на всякий случай явно
set constraints all deferred;

with base as (
  select
    id, code, price_rub, effective_from, effective_to,
    lead(effective_from) over (partition by code order by effective_from, id) as next_from,
    row_number() over (partition by code, effective_from order by id desc) as rn_same_from
  from public.product_prices
),
plan as (
  select
    id, code, effective_from, effective_to, next_from, rn_same_from,
    case
      -- duplicates: удалить rn>1 (оставляем max(id))
      when rn_same_from > 1 then null

      -- last row: сохраняем effective_to как есть (если валиден), иначе делаем open
      when next_from is null then
        case
          when effective_to is null then null
          when effective_to <= effective_from then null
          else effective_to
        end

      -- non-last rows: подрезаем overlap и закрываем “лишние open”
      else
        case
          when next_from <= effective_from then null
          when effective_to is null then next_from
          when effective_to <= effective_from then next_from
          when effective_to > next_from then next_from
          else effective_to
        end
    end as fixed_to
  from base
),
dupes as (
  select id, effective_from
  from plan
  where rn_same_from > 1
),
fixes as (
  select id, effective_from, fixed_to
  from plan
  where rn_same_from = 1
    and (
      (fixed_to is null and effective_to is not null)
      or (fixed_to is not null and effective_to is null)
      or (fixed_to is not null and effective_to is not null and fixed_to <> effective_to)
    )
)
-- 1) delete duplicates
delete from public.product_prices pp
using dupes d
where pp.id = d.id and pp.effective_from = d.effective_from;

-- 2) update effective_to
update public.product_prices pp
set effective_to = f.fixed_to
from fixes f
where pp.id = f.id and pp.effective_from = f.effective_from;

commit;
```

### 5.3 Почему сценарий повторяемый (idempotent)

- Дубликаты удаляются один раз; повторный запуск не найдёт `rn_same_from > 1`.
- `effective_to` приводится к детерминированному `fixed_to`; повторный запуск не создаёт новых изменений.

---

## 6) Post-checks (валидация после remediation)

### 6.1 Инварианты (должно быть 0)

```sql
-- invalid ranges
select count(*) as invalid_ranges
from public.product_prices
where effective_to is not null and effective_to <= effective_from;

-- multiple open intervals
select count(*) as codes_with_multiple_open
from (
  select code
  from public.product_prices
  where effective_to is null
  group by code
  having count(*) > 1
) t;

-- overlaps via window
with ordered as (
  select
    code, effective_from, effective_to,
    lag(effective_to) over (partition by code order by effective_from, id) as prev_to
  from public.product_prices
)
select count(*) as overlaps
from ordered
where prev_to is not null and prev_to > effective_from;

-- duplicate starts
select count(*) as duplicated_starts
from (
  select code, effective_from
  from public.product_prices
  group by code, effective_from
  having count(*) > 1
) t;
```

### 6.2 Guardrails (ожидаем “проходит”)

Если remediation завершилась `COMMIT` без ошибок, значит constraint trigger `trg_product_prices_no_overlap` и constraint `chk_product_prices_valid_range` успешно отработали.

Рекомендуемый smoke:
- повторно прогнать мигратор (идемпотентность):
  - `make db-migrate`
- прогнать интеграционные тесты:
  - `make test-int-noslow` (или `make test-int`)

---

## 7) Rollback (откат)

### 7.1 До commit

Если вы видите ошибки во время apply-сценария — выполните:

```sql
rollback;
```

### 7.2 После commit

Варианты:

1) Восстановление из `pg_dump` (предпочтительно) — восстановить таблицу(ы) целиком.
2) Восстановление из backup-table:

```sql
begin;
lock table public.product_prices in access exclusive mode;

-- ВНИМАНИЕ: этот шаг удалит текущие данные истории цен.
truncate table public.product_prices;

insert into public.product_prices (id, code, price_rub, effective_from, effective_to)
select id, code, price_rub, effective_from, effective_to
from public.product_prices_backup__before_effective_ranges;

commit;
```

---

## 8) Мониторинг (после стабилизации)

Минимум (read-only): раз в сутки сохранять метрики количества нарушений (до 0) из раздела 3.1.

Рекомендация для интеграции:
- добавить job в Ops (или cron на стенде), которая пишет:
  - `invalid_ranges`
  - `codes_with_multiple_open`
  - `duplicated_starts`
  - `overlaps_via_prev`
- при ненулевых значениях — поднимать alert и фиксировать “source file / run_id” на уровне Daily Import (следующий этап hardening).
