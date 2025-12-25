# Import Orchestrator: поток выполнения и компоненты

## Контекст

Импорт прайс-листа запускается через **Import Orchestrator**, который:
1) регистрирует попытку импорта в `import_runs`,
2) (best-effort) создаёт/подвязывает `ingest_envelope`,
3) выполняет ETL (в т.ч. legacy-adapter),
4) фиксирует итоговый статус и метрики в `import_runs`,
5) обеспечивает идемпотентность.

---

## 1) Высокоуровневый поток

1. **CLI**: `python -m scripts.run_import_orchestrator ...`
2. `scripts/import_orchestrator.py`:
   - делает idempotency-check через Run Registry;
   - создаёт envelope (если возможно) и прикрепляет к `import_runs.envelope_id`;
   - запускает импорт-функцию `import_fn(conn, supplier, file_path, as_of_date, run_id, envelope_id=...)`;
   - сохраняет нормализованные метрики (whitelist) в `import_runs`.
3. **ETL / Adapter**:
   - `scripts/import_targets/run_daily_adapter.py` вызывает `etl/run_daily.py::run_etl(...)`;
   - adapter нормализует legacy-метрики (`processed_rows` → `total_rows_processed`).

---

## 2) Idempotency: как именно «пропускается» повтор

Idempotency-ключ в Run Registry: **(supplier, as_of_date, file_sha256)**.

Поведение:
- Если существует **SUCCESS**-прогон для той же тройки `(supplier, as_of_date, file_sha256)` — orchestrator:
  - **не запускает** ETL,
  - создаёт новую запись `import_runs` со статусом `skipped`,
  - переносит `envelope_id` из last_success (фикс PR-3).
- Если `as_of_date` тот же, но файл *другой* (другой `file_sha256`) — это считается *новой* поставкой данных, ETL выполняется.

---

## 3) Ingest Envelope: best-effort и переиспользование

`scripts/ingest_envelope.py::create_ingest_envelope_best_effort`:
- если таблицы `public.ingest_envelope` нет — envelope не создаётся (импорт продолжается);
- если таблица есть — пытается:
  1) `INSERT DEFAULT VALUES RETURNING envelope_id`,
  2) fallback: column-aware insert с вычислением `file_sha256`, `file_size_bytes`, `supplier`, `as_of_date`, `metadata` и др.,
  3) при `UniqueViolation(file_sha256)` — читает существующий `envelope_id` по `file_sha256`.

В результате envelope обычно **переиспользуется для одинакового файла** (одинаковый sha256), даже если вы запускаете импорт для разных `as_of_date`.

---

## 4) Метрики (whitelist) и их нормализация

Orchestrator сохраняет только «разрешённые» метрики в `import_runs` (whitelist).

Для DreemWine / legacy ETL актуальные метрики:
- `total_rows_processed` — число валидных строк, реально обработанных ETL,
- `rows_skipped` — строк входа минус валидные/обработанные.

Adapter (`run_daily_adapter.py`) делает нормализацию:
- `processed_rows` → `total_rows_processed`
- `rows_skipped` → `rows_skipped`

---

## 5) Минимальный «операционный» пример

Импорт (однократно):

```powershell
python -m scripts.run_import_orchestrator `
  --supplier "dreemwine" `
  --file "data/inbox/2025_12_10 Прайс_Легенда_Виноделия.xlsx" `
  --as-of-date "2025-12-10" `
  --import-fn "scripts.import_targets.run_daily_adapter:import_with_run_daily"
```

Повтор **того же файла** с тем же `as_of_date`:

- ETL не выполнится;
- появится новая запись в `import_runs` со `status=skipped`;
- `envelope_id` будет тем же, что у последнего `success`.

---

## 6) Mapping DreemWine

Файл: `etl/mapping_template.json`

Ключевые параметры:
- `sheet: "Основной"`
- `header_row: 3`
- `mapping.price_rub: "Цена со скидкой"`

ETL использует mapping-template в первую очередь; если он не «сходится» по колонкам, включается fallback-эвристика по алиасам.
