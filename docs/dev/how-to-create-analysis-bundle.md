# Как создать analysis bundle

**Analysis bundle** — это ZIP‑архив со снимком репозитория (tracked‑файлы) и диагностическими Git‑метаданными (status/diff/log/untracked) для ревью и отладки.

Архив собирается скриптом `scripts/bundle.ps1` и сохраняется в `./_bundles/` (по умолчанию).

---

## Быстрый старт через Makefile

Запускайте из корня репозитория:

- Базовый бандл (без `static/`):
  ```bash
  make bundle
  ```

- Бандл с включением `static/`:
  ```bash
  make bundle-static
  ```

- Полный бандл (static + `pip freeze`):
  ```bash
  make bundle-full
  ```

Если хотите изменить директорию вывода:
```bash
make bundle BUNDLE_OUT_DIR=./_bundles
```

---

## Запуск напрямую через PowerShell (без make)

### Windows PowerShell
- Базовый:
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bundle.ps1
  ```

- С включением `static/`:
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bundle.ps1 -IncludeStatic
  ```

- Полный (static + `pip freeze`):
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bundle.ps1 -IncludeStatic -IncludePipFreeze
  ```

### PowerShell 7 (pwsh)
Аналогично, но командой `pwsh`:
```powershell
pwsh -NoProfile -File scripts/bundle.ps1
```

### Изменить директорию вывода
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bundle.ps1 -OutDir ".\_bundles"
```

---

## Что входит в архив

Внутри ZIP обычно присутствуют:

### 1) Git‑метаданные
- `bundle_git_status.txt` — `git status --porcelain=v1`
- `bundle_git_diff.txt` — изменения в рабочем дереве (unstaged)
- `bundle_git_diff_staged.txt` — staged‑изменения
- `bundle_git_diff_stat.txt` / `bundle_git_diff_staged_stat.txt` — краткая статистика по diff
- `bundle_git_untracked.txt` — untracked файлы (`git ls-files -o --exclude-standard`)
- `bundle_git_log.txt` — последние коммиты
- `bundle_git_head.txt`, `bundle_git_branches.txt`, `bundle_git_remotes.txt`

### 2) Информация о Python‑окружении
- `bundle_python_version.txt`
- `bundle_pip_freeze.txt` (только при `-IncludePipFreeze` / `make bundle-full`)

### 3) Снимок проекта
- tracked‑файлы из репозитория (с исключениями: `.venv/`, кэши, `.env*`, ключи `*.pem/*.key/*.pfx` и т.п.)
- по умолчанию `static/` исключён, но включается флагом `-IncludeStatic` / `make bundle-static`

### 4) Манифест состава
- `bundle_included_files.txt` — список файлов, включённых в бандл

---

## Частые проблемы и решения

### В архиве “не те изменения”
Проверьте, что вы запускаете сборку **после** нужных правок. Бандл собирается из текущего состояния working tree.

### Архив содержит `static/`, хотя вы не хотели
Используйте `make bundle` (без `bundle-static`) или запуск без `-IncludeStatic`.

### Нужны и staged, и unstaged изменения
Это уже входит в метаданные (`bundle_git_diff_staged.txt` + `bundle_git_diff.txt`).
