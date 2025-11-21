# Wine Assistant — Roadmap v2 (Sprint 7+) — согласовано и уточнено

> Эта версия учитывает твои приоритеты и комментарии. Внёс: TZ = `Europe/Moscow`, битемпоральность (явные колонки), правило фолбэка цены, ключ `(supplier_id, sku)`, Must/Should/Could-таблицу, новые Issues #84, #92, #93, #95, #96, #97, #98, #99, #100 и их DoD. Добавлены примеры конфигов (YAML), авто‑партиции, миграции, TLS/секьюрити, мониторинг партиций и ETL‑дашборд.

## TL;DR
- **Ниша:** PIM/Pricebook + история цен/остатков, ETL из вложений (ежедневно, будни), Swagger API.
- **Главные изменения:** bitemporal (`effective_date`, `ingested_at`), идемпотентный импорт (hash + envelope), кеги/розлив, мастер‑данные из PDF, DQ‑гейты с карантином, фасеты через MatView, версионирование API, партиционирование истории, секьюрность (secrets/TLS/JWT).
- **TZ планировщика:** `Europe/Moscow`.

---

## 0) Must / Should / Could (по твоему приоритету)
**Must‑have (делаем сейчас):**
- #84 **Data Quality Gates & Quarantine**
- #92 **Partitioning & Retention**
- #95 **Security & Secrets**
- (правки схемы) **битемпоральность**, **фолбэк цены**, **ключ `(supplier_id, sku)`**, **TZ**

**Should‑have (Sprint 8–9):**
- #93 **Data Lineage (почта/вложение)**
- #96 **API Versioning & Deprecation**
- #97 **Golden Files (format drift)**
- #99 **ETL Health Dashboard**

**Could‑have (Sprint 10+):**
- #94 **Backfill tool**
- #98 **Materialized Facets (оптимизация)**
- #100 **Per‑user Rate Limiting**

---

## 1) Политики и SLO
- **Bitemporal:** в `product_prices`, `inventory_history`, `serving_prices` храним `effective_date` **и** `ingested_at`.
- **Idempotency:** уникальность загрузки по `source_file_hash` (SHA256) + `(supplier_id, price_date)`.
- **Фолбэк цены:** `price_final_rub := price_list_rub`, если скидочная пустая/некорректна.
- **SLO:** *прайс → API* ≤ **10 минут**; p95 `/products` < **200 мс**; ≥ **95%** строк проходят DQ; p95 ETL (end‑to‑end) < **6 минут**.
- **TZ:** `Europe/Moscow` (импорт, фасеты, отчёты).

---

## 2) Конфиг DQ‑гейтов (пример, YAML)
```yaml
dq:
  per_row:
    require_sku: true
    min_price_list_rub: 0
    min_price_final_rub: 0
    abv_pct_range: [0.1, 100.0]
    volume_l_range: [0.05, 30.0]
    stock_free_nonnegative: true
    obey_masterdata:
      abv_pct_tolerance: 0.5
      volume_l_exact: true
  per_file:
    min_rows: 50
    min_recognized_headers_pct: 0.90
    max_empty_sku_pct: 0.01
    max_empty_price_pct: 0.05
  quarantine:
    path: "artifacts/dq/${YYYY}-${MM}-${DD}/"
    alert: "sentry" # или "email", "slack"
```

---

## 3) Модель данных и миграции (выдержки)
### 3.1 Источник/идемпотентность
```sql
create table ingest_envelope (
  id bigserial primary key,
  supplier_id int not null references supplier(id),
  source_filename text not null,
  source_file_hash text not null unique,
  received_via text not null,                -- 'email' | 'manual' | 'telegram'
  sender_address text,
  subject text,
  received_at timestamptz,
  saved_to text,
  created_at timestamptz default now()
);

create table price_list (
  id bigserial primary key,
  supplier_id int not null references supplier(id),
  price_date date not null,
  envelope_id bigint references ingest_envelope(id),
  created_at timestamptz default now(),
  unique (supplier_id, price_date, envelope_id)
);
```

### 3.2 Товары (обогащение)
```sql
alter table product
  add column if not exists vivino_url text,
  add column if not exists rating_vivino numeric(3,1),
  add column if not exists certificate text;

create unique index if not exists ux_product_supplier_sku
  on product (supplier_id, sku);
```

### 3.3 История (битемпоральность + партиции)
```sql
create table product_prices (
  id bigserial primary key,
  product_id int not null references product(id),
  effective_date date not null,
  ingested_at timestamptz not null default now(),
  price_list_rub numeric(12,2),
  price_final_rub numeric(12,2)
) partition by range (effective_date);

create table inventory_history (
  id bigserial primary key,
  product_id int not null references product(id),
  effective_date date not null,
  ingested_at timestamptz not null default now(),
  stock_total numeric(12,3),
  reserved numeric(12,3),
  stock_free numeric(12,3)
) partition by range (effective_date);

-- пример партиции
create table product_prices_2025_01
  partition of product_prices
  for values from ('2025-01-01') to ('2025-02-01');
```

### 3.4 Кеги/розлив
```sql
create table serving_prices (
  id bigserial primary key,
  product_id int not null references product(id),
  size_ml int not null,                      -- 125, 150, 750, 1000
  price_rub numeric(12,2) not null,
  effective_date date not null,
  ingested_at timestamptz not null default now(),
  unique(product_id, size_ml, effective_date)
);
```

### 3.5 Авто‑создание партиций (PG 11+)
```sql
create or replace function ensure_month_partition(base regclass, month date) returns void as $$
declare
  tbl text := to_char(month, 'YYYY_MM');
begin
  execute format('create table if not exists %s_%s partition of %s for values from (%L) to (%L)',
    base::text, tbl, base::text, date_trunc('month', month)::date, (date_trunc('month', month) + interval '1 month')::date);
end; $$ language plpgsql;
```

### 3.6 Мониторинг размеров партиций
```sql
select inhrelid::regclass as part,
       pg_size_pretty(pg_total_relation_size(inhrelid)) as size
from pg_inherits where inhparent = 'product_prices'::regclass
order by 1;
```

---

## 4) ETL (будние дни, Europe/Moscow)
- Импорт вложений → `ingest_envelope`; вычисление `sha256`.
- Нормализация (листы: Основной/Кег/Крепкий алкоголь), мэппинг YAML, чистка чисел/дат.
- DQ‑гейты: строка/файл; карантин с отчётом и алертом (Sentry/Slack).
- Upsert: `supplier/product`; `price_list`; `product_prices`/`inventory_history` по `effective_date`; `serving_prices`.
- Архив: `data/archive/YYYY-MM-DD/` + hash.
- **Cron:** `10 8 * * 1-5  python -m wine_assistant.jobs.ingest_dw_price`.

---

## 5) API v1, фасеты, версионирование
- `/api/v1/products` (фильтры: страна/регион/стиль/сорт/ABV/объём/поставщик).
- `/api/v1/products/{id}`; `/prices?from=&to=`; `/servings`; `/stocks?date=&location=`.
- Матвью `mv_products_facets`; `REFRESH CONCURRENTLY` после импорта.
- Версии: v1 текущая; breaking → v2 (overlap 90 дней); заголовки `Sunset`, `Deprecation`, `Link`.

---

## 6) Security & Ops (минимум продакшн)
- **Secrets:** Docker secrets/`.env` вне репо; gitleaks в CI.
- **TLS:** HTTPS (например, Caddy/Traefik + Let’s Encrypt).
- **JWT:** ротация ключей, `exp ≤ 24h`, read‑only роли.
- **CORS:** whitelist доменов.
- **SQL‑инъекции:** parameterized queries, no string concat.
- **Rate limit:** базовый глобальный + (#100) per‑user/role в Redis.

---

## 7) Новые Issues (готовые карточки)
### #84 Data Quality Gates & Quarantine (Must)
**Правила:** см. YAML выше.
**Артефакты:** `dq_quarantine`, отчёт в `artifacts/dq/`.
**Alerts:** Sentry/Slack.
**DoD:** «битый» файл/строки не в БД; отчёт и алерт сформированы.

### #92 Partitioning & Retention (Must)
**Партиции:** RANGE по `effective_date` (месяц).
**Ретенция:** 36 мес онлайн; старше — Parquet (S3/MinIO).
**Automation:** функция `ensure_month_partition`, крон 1‑го числа.
**DoD:** p95 истории < 200 мс на 1M+ строк.

### #95 Security & Secrets (Must)
**CI:** gitleaks. **TLS:** HTTPS. **JWT:** ротация, `exp ≤ 24h`.
**Логи:** маскирование PII. **CORS:** whitelist. **SQL:** параметризация.
**DoD:** CI чист; TLS включён; логи без PII; токены протухают корректно.

### #93 Data Lineage (Should)
`ingest_envelope` при приёме файла; связываем в `price_list`.
**DoD:** по любой записи истории видны sender/subject/hash/путь.

### #96 API Versioning (Should)
`/api/v1`; при breaking → `/api/v2` + заголовки депрекации, 90 дней overlap.
**DoD:** Swagger v1; шаблон уведомления о депрекации.

### #97 Golden Files (Should)
Набор эталонных XLSX + сравнение JSON‑вывода в CI.
**DoD:** format drift ловится в CI.

### #99 ETL Health Dashboard (Should)
**Метрики:** p50/p95/p99 времени импорта, % карантина, число файлов/сутки, lag от inbox до API.
**Визуализация:** Grafana; дневной Slack/email дайджест.
**DoD:** сбой ETL заметен < 5 мин.

### #94 Backfill tool (Could)
CLI для архивов, идемпотентность по hash, скоринг качества.
**DoD:** история догружена, граф цен сходится с эталоном.

### #98 Materialized Facets (Could)
`mv_products_facets`, индексы, `REFRESH CONCURRENTLY` после импорта.
**DoD:** p95 `/products/facets` < 100 мс.

### #100 Per‑user Rate Limiting (Could)
Redis‑счётчики; тарифы Free/Pro/Enterprise; `X‑RateLimit‑*` заголовки.
**DoD:** превышение квоты → `429` с `Retry‑After`.

---

## 8) Приложение
**Индексы:**
```sql
create index if not exists ix_prices_product_effdate on product_prices (product_id, effective_date desc);
create index if not exists ix_invhist_product_effdate on inventory_history (product_id, effective_date desc);
create index if not exists ix_envelope_hash on ingest_envelope (source_file_hash);
```

**Cron (Linux, Europe/Moscow):**
```
10 8 * * 1-5 /usr/bin/python -m wine_assistant.jobs.ingest_dw_price >> /var/log/wine-assistant/ingest.log 2>&1
```

**Политика ответов API:**
- Rate‑limit заголовки: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`.
- Ошибки: `422` (валидация), `429` (лимиты), `5xx` (непредвиденные).
