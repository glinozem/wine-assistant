# Observability Stack для Wine Assistant

Стек наблюдаемости на базе **Grafana + Loki + Promtail** для мониторинга Wine Assistant API.

## Компоненты

| Сервис | Описание | Порт |
|--------|----------|------|
| **Grafana** | Визуализация и дашборды | `localhost:15000` |
| **Loki** | Хранение и индексация логов | внутренний (3100) |
| **Promtail** | Сбор Docker логов | — |

## Быстрый старт

```bash
# Запуск всего стека (API + Observability)
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d

# Открыть Grafana
open http://localhost:15000
# Логин: admin / Пароль: admin
```

## Структура файлов

```
observability/
├── promtail-config.yml                    # Конфиг сбора логов
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── datasources.yml            # Автоподключение Loki
│   │   └── dashboards/
│   │       └── dashboards.yml             # Конфиг загрузки дашбордов
│   └── dashboards/
│       └── wine-assistant-api.json        # Дашборд API мониторинга
```

## Дашборд "Wine Assistant API Monitoring"

### Панели

| Панель | Описание |
|--------|----------|
| **Requests per Minute** | Количество запросов в минуту |
| **Avg Response Time** | Среднее время ответа (ms) |
| **Requests by Status Code** | Распределение по HTTP статусам |
| **Requests by Path** | Распределение по эндпоинтам |
| **Top Slowest Endpoints** | Самые медленные эндпоинты |
| **Errors by Event Type** | Ошибки по типам событий |
| **Recent Requests** | Последние запросы (логи) |
| **Error Logs** | Логи с уровнем ERROR |

### LogQL запросы

```logql
# Все логи API
{job="docker-logs"} |= "api.app" | json

# Ошибки
{job="docker-logs", level="ERROR"}

# Запросы по статус-коду
sum by (status_code) (count_over_time({job="docker-logs"} |= "http_request_completed" | json | status_code != "" [5m]))

# Среднее время ответа
avg(avg_over_time({job="docker-logs"} |= "http_request_completed" | json | unwrap duration_ms [5m]))

# Запросы конкретного SKU
{job="docker-logs"} |= "http_request_completed" | json | sku_code = "D010210"
```

## Labels (низкая кардинальность)

Следующие поля доступны как labels для быстрой фильтрации:
- `job` — всегда `docker-logs`
- `level` — INFO, WARNING, ERROR
- `event` — тип события (http_request_completed, и т.д.)
- `service` — wine-assistant-api
- `http_method` — GET, POST, PUT, DELETE

## High-cardinality поля

Эти поля НЕ являются labels (для избежания cardinality explosion), но доступны через `| json`:
- `request_id`
- `http_path`
- `sku_code`
- `status_code`
- `duration_ms`
- `dt_from`, `dt_to`

## Alerting

Alert Rule "API Errors" настроен в Grafana:
- **Условие:** любые ERROR логи за 5 минут
- **Интервал проверки:** 1 минута
- **Статусы:** Normal (зелёный), Firing (красный)

Для внешних уведомлений настройте Contact Points в Grafana:
`Alerting → Contact points → Add contact point`

## Управление

```bash
# Перезапуск только Promtail (после изменения конфига)
docker compose -f docker-compose.yml -f docker-compose.observability.yml restart promtail

# Логи Promtail
docker compose -f docker-compose.yml -f docker-compose.observability.yml logs promtail --tail=50

# Полный рестарт observability стека
docker compose -f docker-compose.yml -f docker-compose.observability.yml restart loki grafana promtail

# Остановка только observability (API продолжит работать)
docker compose -f docker-compose.observability.yml down
```

## Troubleshooting

### "No data" в панелях
1. Проверьте, что API генерирует логи: `docker logs wine-assistant-api --tail=20`
2. Проверьте Promtail: `docker logs wine-assistant-promtail --tail=20`
3. В Grafana Explore выполните: `{job="docker-logs"}`

### "maximum of series (500) reached"
Это означает слишком много уникальных комбинаций labels. Убедитесь, что `promtail-config.yml` НЕ содержит high-cardinality поля (`request_id`, `http_path`) как labels.

### Grafana не видит Loki
1. Проверьте, что Loki запущен: `docker ps | grep loki`
2. В Grafana: `Connections → Data sources → loki → Save & Test`
