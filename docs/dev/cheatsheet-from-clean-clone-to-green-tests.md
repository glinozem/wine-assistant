# Шпаргалка: от чистой среды до зелёных тестов (wine-assistant)

Документ для себя/тиммейта: как на **Windows** с Docker и Python быстро поднять проект, наполнить БД и получить зелёные тесты.

Путь к проекту в примерах:

```powershell
D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine-assistant
```

---

## 0. Предварительные требования (один раз)

Нужно, чтобы были установлены:

- **Git**
- **Python 3.11+**
- **Docker Desktop** (c Docker Compose)
- Желательно: **PowerShell** (стандартно есть в Windows 10/11)

Клонируем репозиторий и ставим зависимости:

```powershell
cd D:\Documents\JetBrainsIDEProjects\PyCharmProjects

git clone https://github.com/glinozem/wine-assistant.git
cd .\wine-assistant

# создаём виртуальное окружение
python -m venv .venv
.\.venv\Scripts\activate

# ставим зависимости
pip install -r requirements.txt
```

Дальше все команды считаем выполняемыми из корня проекта в активированном `.venv`.

---

## 1. Полная пересборка окружения Docker

Сносим старые контейнеры и volume'ы, поднимаем всё заново.

```powershell
cd D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine-assistant

# Остановить и удалить контейнеры + данные Postgres
docker compose down -v

# Поднять стек (db + migrator + api + adminer)
docker compose up -d
```

Проверяем статусы:

```powershell
docker compose ps
```

Ожидаем примерно такое:

- `wine-assistant-db` — `Up (...healthy)`
- `wine-assistant-api` — `Up (...healthy)`
- `wine-assistant-adminer` — `Up`
- `wine-assistant-migrator` — отработал и вышел (`exited (0)`) или уже не отображается (one-shot сервис).

Если `db` или `api` не в `healthy`, смотрим логи:

```powershell
docker compose logs db
docker compose logs api
```

---

## 2. Загрузка прайс-листов в БД

Файлы **Excel-прайсов** лежат в:

```text
data\inbox\*.xlsx
```

Мы успешно загружали такие файлы (без копии января):

- `data\inbox\2025_06_03 Прайс_Легенда_Виноделия.xlsx`
- `data\inbox\2025_06_25 Прайс_Легенда_Виноделия.xlsx`
- `data\inbox\2025_08_06 Прайс_Легенда_Виноделия.xlsx`
- `data\inbox\2025_08_19 Прайс_Легенда_Виноделия.xlsx`
- `data\inbox\2025_09_29 Прайс_Легенда_Виноделия.xlsx`
- `data\inbox\2025_10_22 Прайс_Легенда_Виноделия.xlsx`
- `data\inbox\2025_10_27 Прайс_Легенда_Виноделия.xlsx`

### Вариант 1. Загрузить каждый файл явно (рекомендуемо для воспроизводимости)

```powershell
.\.venv\Scripts\activate
cd D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine-assistant

python -m scripts.load_csv --excel ".\data\inbox\2025_06_03 Прайс_Легенда_Виноделия.xlsx"
python -m scripts.load_csv --excel ".\data\inbox\2025_06_25 Прайс_Легенда_Виноделия.xlsx"
python -m scripts.load_csv --excel ".\data\inbox\2025_08_06 Прайс_Легенда_Виноделия.xlsx"
python -m scripts.load_csv --excel ".\data\inbox\2025_08_19 Прайс_Легенда_Виноделия.xlsx"
python -m scripts.load_csv --excel ".\data\inbox\2025_09_29 Прайс_Легенда_Виноделия.xlsx"
python -m scripts.load_csv --excel ".\data\inbox\2025_10_22 Прайс_Легенда_Виноделия.xlsx"
python -m scripts.load_csv --excel ".\data\inbox\2025_10_27 Прайс_Легенда_Виноделия.xlsx"
```

В успешном случае лог для каждого файла заканчивается примерно так:

```text
[OK] Import completed successfully
   Envelope ID: <uuid>
   Rows processed (good): NNN
   Rows failed (quarantine): 0
   Effective date: YYYY-MM-DD
```

### Вариант 2. Автоматически пройти по всем XLSX в папке (PowerShell)

> ВАЖНО: так загрузятся **все** xlsx в `data\inbox`. Если там лежат экспериментальные/старые файлы
> (например, копия от 2025-01-20, см. ниже), лучше использовать Вариант 1 или явно отфильтровать список.

```powershell
Get-ChildItem -Path .\data\inbox -Filter *.xlsx | ForEach-Object {
    Write-Host ">> Загружаю" $_.FullName
    python -m scripts.load_csv --excel $_.FullName
}
```

### Что с файлом «Копия 2025_01_20 Прайс_Легенда_Виноделия.xlsx»?

При загрузке **после** более новых прайсов он даёт ошибку в функции `upsert_price`:

```text
psycopg2.errors.DataException: range lower bound must be less than or equal to range upper bound
```

Это связано с историей цен (диапазоны дат). Для текущего набора тестов этот файл **не обязателен**, поэтому
в стабильном сценарии его можно либо:

- **не загружать**, либо
- загружать **первым** (до всех прайсов 2025-06-03 и далее), если понадобится полная история с января.

---

## 3. Проверка карантина прайс-листа

Таблица для «проблемных» строк называется `price_list_quarantine`.

Посмотреть её структуру:

```powershell
docker compose exec db psql -U postgres -d wine_db `
  -c "\d price_list_quarantine"
```

Посмотреть последние строки (если есть):

```powershell
docker compose exec db psql -U postgres -d wine_db `
  -c "SELECT id, envelope_id, code, dq_errors, created_at
      FROM price_list_quarantine
      ORDER BY created_at DESC
      LIMIT 50;"
```

В успешном прогоне, который приводил к зелёным тестам, результат был:

```text
(0 rows)
```

то есть DQ-проверки прошли, и в карантин ничего не попало.

---

## 4. Запуск тестов

Все команды — из корня проекта с активированным `.venv`.

### 4.1. Юнит-тесты

```powershell
.\.venv\Scripts\activate
cd D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine-assistant

pytest tests/unit -q
```

Ожидание: 100+ тестов `passed`, без `failed`. Пример реального вывода:

```text
========================================== test session starts ===========================================
...
collected 101 items

...
========================================== 101 passed in 44.46s ==========================================
```

### 4.2. Интеграционные тесты с Postgres

Интеграционные тесты включаются переменной `RUN_DB_TESTS=1`.

```powershell
$env:RUN_DB_TESTS = "1"
pytest -m "integration" -vv
```

Пример реального результата:

```text
============================= 18 passed, 134 deselected in 118.79s (0:01:58) =============================
```

### 4.3. Полный прогон всех тестов (API + unit + integration)

```powershell
pytest -q
```

Пример реального результата «зелёного» прогона:

```text
==================================== 152 passed in 157.32s (0:02:37) =====================================
```

---

## 5. Если что-то идёт не так

### 5.1. Тесты не могут подключиться к БД

Проверяем, что контейнеры живы и БД `healthy`:

```powershell
docker compose ps
```

Если БД слушает нестандартный порт (в docker-compose обычно проброшен `15432` на localhost),
можно явно прокинуть переменные окружения перед pytest (опционально, если это не делает сама конфигурация):

```powershell
$env:PGHOST = "localhost"
$env:PGPORT = "15432"
$env:PGUSER = "postgres"
$env:PGPASSWORD = "postgres"
$env:PGDATABASE = "wine_db"
```

и затем:

```powershell
$env:RUN_DB_TESTS = "1"
pytest -m "integration" -vv
```

### 5.2. Падает `load_csv` c ошибками `psycopg2`/`upsert_price`

- Проверить, не загружаете ли вы старый прайс **после** новых (как в случае с `Копия 2025_01_20 ...`).
- При необходимости пересобрать окружение и загрузить прайсы в другом порядке:

  ```powershell
  docker compose down -v
  docker compose up -d
  # затем загрузка файлов заново в нужном порядке
  ```

---

## 6. TL;DR — минимальный сценарий «зелёный прогон»

```powershell
cd D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine-assistant
.\.venv\Scripts\activate

# 1. Пересоздать Docker-окружение
docker compose down -v
docker compose up -d

# 2. Загрузить прайс-листы (без проблемной копии 2025-01-20)
python -m scripts.load_csv --excel ".\data\inbox\2025_06_03 Прайс_Легенда_Виноделия.xlsx"
python -m scripts.load_csv --excel ".\data\inbox\2025_06_25 Прайс_Легенда_Виноделия.xlsx"
python -m scripts.load_csv --excel ".\data\inbox\2025_08_06 Прайс_Легенда_Виноделия.xlsx"
python -m scripts.load_csv --excel ".\data\inbox\2025_08_19 Прайс_Легенда_Виноделия.xlsx"
python -m scripts.load_csv --excel ".\data\inbox\2025_09_29 Прайс_Легенда_Виноделия.xlsx"
python -m scripts.load_csv --excel ".\data\inbox\2025_10_22 Прайс_Легенда_Виноделия.xlsx"
python -m scripts.load_csv --excel ".\data\inbox\2025_10_27 Прайс_Легенда_Виноделия.xlsx"

# 3. Проверить (опционально), что карантин пуст
docker compose exec db psql -U postgres -d wine_db `
  -c "SELECT id, envelope_id, code, dq_errors, created_at FROM price_list_quarantine ORDER BY created_at DESC LIMIT 50;"

# 4. Юнит-тесты
pytest tests/unit -q

# 5. Интеграционные тесты с БД
$env:RUN_DB_TESTS = "1"
pytest -m "integration" -vv

# 6. Полный прогон (опционально)
pytest -q
```

Этого достаточно, чтобы за 2–3 минуты поднять всё с нуля и убедиться, что проект в состоянии «все тесты зелёные».
