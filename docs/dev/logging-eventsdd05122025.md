# Спецификация лог-событий (logging-events.md)

## Назначение документа

Данный документ описывает **единый формат событий логирования (`event`)**, используемый в сервисе **Wine Assistant API**, а также структуру полей, общих для всех логов.

Цель:

- стандартизировать формат логов для удобства анализа;
- обеспечить консистентность при построении дашбордов в **Kibana / Grafana**;
- облегчить трассировку запросов через `request_id`;
- описать все существующие события и места их возникновения в коде.

---

## Общий формат лог-событий

Каждое событие содержит следующие базовые поля:

| Поле | Тип | Описание |
|------|------|----------|
| `event` | string | машинное имя события (snake_case) |
| `service` | string | всегда `"wine-assistant-api"` |
| `request_id` | string | сквозной ID запроса (совпадает с заголовком `X-Request-ID`) |
| `http_method` | string | HTTP-метод запроса (`GET`, `POST`, …) |
| `http_path` | string | путь запроса (`/api/v1/...`) |
| `error` | string | текст ошибки (если есть) |
| `error_type` | string | тип исключения |
| `error_message` | string | сообщение исключения |

Дополнительные доменные поля:

| Поле | Описание |
|------|----------|
| `sku_code` | артикул товара |
| `query` | поисковый запрос |
| `limit`, `offset` | параметры пагинации |
| `in_stock` | фильтр наличия |
| `dt_from`, `dt_to` | временные диапазоны для историй |

---

# 1. Инфраструктурные события

## `unhandled_exception`
**Когда:** происходит любое необработанное исключение.
**Где:** глобальный error handler.
**Уровень:** ERROR.

---

## `invalid_api_key`
**Когда:** пользователь передал неверный API ключ.
**Уровень:** WARNING.
**Дополнительные поля:** `client_ip`, `provided_key_prefix`.

---

# 2. Readiness / Health

## `readiness_db_unavailable`
**Когда:** сервис работает, но не может подключиться к БД.
**Уровень:** ERROR.

---

## `readiness_check_failed`
**Когда:** случилось неожиданное исключение при readiness.
**Уровень:** ERROR.

---

# 3. Simple search (`/search`)

## `simple_search_db_unavailable`
**Когда:** БД недоступна.
**Уровень:** ERROR.

---

## `simple_search_failed`
**Когда:** ошибка выполнения поискового запроса.
**Уровень:** ERROR.
**Дополнительные поля:** `query`, `limit`.

---

# 4. Catalog search (`/api/v1/products/search`)

## `catalog_search_db_unavailable`
**Когда:** БД недоступна для каталожного поиска.
**Уровень:** ERROR.

---

## `catalog_search_failed`
**Когда:** ошибка выполнения каталожного поиска.
**Уровень:** ERROR.
**Доп. поля:** `query`, `limit`, `offset`, `in_stock`.

---

# 5. SKU карточка товара

## `sku_not_found`
**Когда:** SKU отсутствует — нормальная ситуация.
**Уровень:** INFO.

---

## `sku_lookup_db_unavailable`
**Когда:** не удалось подключиться к БД.
**Уровень:** ERROR.

---

## `sku_lookup_failed`
**Когда:** ошибка выполнения SQL запроса.
**Уровень:** ERROR.

---

# 6. История цен (API)

## `price_history_db_unavailable`
**Когда:** нет соединения с БД.
**Уровень:** ERROR.

---

## `price_history_lookup_failed`
**Когда:** SQL запрос завершился ошибкой.
**Уровень:** ERROR.

---

# 7. История остатков (API)

## `inventory_history_db_unavailable`
**Когда:** БД недоступна.
**Уровень:** ERROR.

---

## `inventory_history_lookup_failed`
**Когда:** SQL запрос завершился ошибкой.
**Уровень:** ERROR.

---

# 8. Экспорт поиска

## `export_search_db_unavailable`
**Когда:** БД недоступна при экспорте поиска.
**Уровень:** ERROR.

---

## `export_search_failed`
**Когда:** ошибка генерации XLSX/PDF/JSON.
**Уровень:** ERROR.

---

# 9. Экспорт SKU

## `export_sku_called`
**Когда:** вызван экспорт SKU.
**Уровень:** INFO.

---

## `export_sku_db_unavailable`
**Когда:** БД недоступна.
**Уровень:** ERROR.

---

## `export_sku_failed`
**Когда:** ошибка генерации PDF/JSON.
**Уровень:** ERROR.

---

# 10. Экспорт истории цен

## `export_price_history_db_unavailable`
**Когда:** БД недоступна.
**Уровень:** ERROR.

---

## `export_price_history_failed`
**Когда:** ошибка генерации XLSX/JSON.
**Уровень:** ERROR.

---

# 11. Экспорт истории остатков

## `export_inventory_history_db_unavailable`
**Когда:** БД недоступна.
**Уровень:** ERROR.

---

## `export_inventory_history_failed`
**Когда:** ошибка генерации XLSX/JSON.
**Уровень:** ERROR.

---

# 12. Примеры запросов в Kibana

### Все ошибки сервиса
```kql
service : "wine-assistant-api" and level : "ERROR"
```

### Ошибки подключения к БД
```kql
event : "*_db_unavailable"
```

### Ошибки экспорта остатков
```kql
event : ("export_inventory_history_failed" or "export_inventory_history_db_unavailable")
```

### Ошибки по конкретному SKU
```kql
sku_code : "D010210"
```

### Поиск всех ошибок за конкретный временной диапазон
```kql
dt_from <= "2025-01-01" and dt_to >= "2025-12-31"
```

### Полная трасса запроса
```kql
request_id : "req_17afc3"
```

---

# Итог

Этот документ — единый источник информации по лог-событиям.
Он помогает DevOps, аналитикам и разработчикам быстро фильтровать и интерпретировать логи сервиса Wine Assistant API.
