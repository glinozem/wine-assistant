# Ops: Daily Import housekeeping

Цель: безопасная ретенция (housekeeping) файлов в директориях Daily Import.

## Что чистим

Зоны:

- inbox: `data/inbox`
- archive: `data/archive`
- quarantine: `data/quarantine`
- logs: `data/logs/daily-import`

Критерий отбора: `mtime` файла (UTC). Удаляются только **файлы** (директории не трогаем).
`.gitkeep` игнорируется.

## Safety model

- По умолчанию: **dry-run** (ничего не удаляет), только печатает план.
- Для фактического удаления нужен флаг `--apply` (или `APPLY=1` в make).
- Guardrail `min-age-days` (по умолчанию 7): если среди кандидатов есть файлы моложе `min-age-days`,
  то без `--force` удаление запрещено (ошибка, exit code 2).

## Make targets

Единая команда:

```bash
make daily-import-housekeeping
```

Параметры (0 = зона отключена):

- `DAYS_INBOX`
- `DAYS_ARCHIVE`
- `DAYS_QUARANTINE`
- `DAYS_LOGS`
- `HK_MIN_AGE_DAYS` (default: 7)
- `APPLY=1` — выполнить удаление
- `FORCE=1` — обойти safety guard

Примеры:

Dry-run (только план):

```bash
make daily-import-housekeeping DAYS_ARCHIVE=90
```

Apply:

```bash
make daily-import-housekeeping DAYS_ARCHIVE=90 APPLY=1
```

Apply + force:

```bash
make daily-import-housekeeping DAYS_ARCHIVE=90 APPLY=1 FORCE=1
```

Deprecated alias:

```bash
make daily-import-cleanup-archive DAYS=90
make daily-import-cleanup-archive DAYS=90 APPLY=1
```

## Direct CLI usage

```bash
python -m scripts.ops_housekeeping --days-archive 90
python -m scripts.ops_housekeeping --days-archive 90 --apply
python -m scripts.ops_housekeeping --days-archive 90 --apply --force
```
