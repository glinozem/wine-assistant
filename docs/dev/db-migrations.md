# DB migrations: канон и guardrails

## Источник истины

- **Schema evolution (источник истины):** `db/migrations/NNNN_*.sql`
- **Bootstrap-only:** `db/init.sql`
  - создаёт только базовые таблицы, которые исторически не создаются миграциями: `public.products`, `public.inventory`;
  - не содержит индексы/constraints/functions/views/прочие таблицы;
  - любые изменения схемы делаются новой миграцией, а не правкой init.sql.

## Layout policy

- Canonical migrations: только `db/migrations/NNNN_*.sql`
- Legacy scripts: только `db/migrations/_legacy/` и **не применяются автоматически**
- Применение — лексикографически по имени файла.

### Нумерация
- Формат: `NNNN_description.sql`
- Дубликаты `NNNN` **допустимы** (исторически в репозитории уже есть), но **не рекомендуются**.
- Для новых миграций используйте следующий свободный номер, чтобы не усложнять ревью.

## Запрет правок уже существующих canonical-миграций

- Canonical-миграции, уже существующие в репозитории, **нельзя редактировать/переименовывать**.
- Если нужно изменить поведение — добавьте новую миграцию.
- CI для PR запрещает изменения файлов `db/migrations/NNNN_*.sql` (кроме добавления новых).

## Идемпотентность

Каждая миграция должна быть безопасна при повторном прогоне:
- `CREATE ... IF NOT EXISTS`
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- `DROP ... IF EXISTS`
- `CREATE OR REPLACE FUNCTION`

Локальная проверка: прогоните мигратор дважды (должен быть “зелёным” второй прогон).

## Как добавить миграцию

1) Создайте файл: `db/migrations/NNNN_short_description.sql`
2) Пишите миграцию идемпотентно (см. выше).
3) Примените локально:
   - Bash: `bash db/migrate.sh`
   - Windows: `.\db\migrate.ps1`
4) Прогоните второй раз (идемпотентность).
5) Запустите тесты.

## CI guardrails (что именно проверяется)

- layout policy (`scripts/check_migrations.py`)
- bootstrap contract для `db/init.sql` (`scripts/check_db_bootstrap_contract.py`)
- запрет правок существующих canonical migrations в PR (git diff check)
- применение миграций на clean DB + идемпотентность `db/migrate.sh` (2 прогона)

## Troubleshooting

### “migration already applied but sha differs”
Причина: вы изменили уже существующую canonical-миграцию. Решение: откатить правку, добавить новую миграцию.

### “VALIDATE CONSTRAINT … is violated” / ошибки из-за неконсистентных данных
Используйте remediation playbook:
- `docs/dev/effective_ranges_remediation.md` — playbook исправления effective ranges в `public.product_prices` (overlap/invalid bounds/duplicate starts) и последующая валидация guardrails.
