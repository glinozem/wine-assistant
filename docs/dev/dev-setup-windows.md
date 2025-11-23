# dev-setup-windows.md — настройка среды разработки на Windows (wine-assistant)

Этот документ описывает **практический путь** для разработчика на Windows:
как с нуля поднять проект, наполнить БД реальными прайсами и получить зелёные тесты,
используя `make` и `docker compose`.

Все примеры ниже даны для PowerShell и структуры проекта вида:

```powershell
D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine-assistant
```

---

## 0. Предварительные требования (один раз)

Нужно установить:

- **Git**
- **Python 3.11+**
- **Docker Desktop** (включая Docker Compose)
- **Chocolatey** (удобно, но не обязательно) — для установки GNU Make
- **PowerShell** (стандартно есть в Windows 10/11)

### 0.1. Установка GNU Make через Chocolatey

Открываем PowerShell **от имени администратора** и выполняем:

```powershell
choco install make
```

После установки в новом окне PowerShell проверяем:

```powershell
make --version
```

Ожидаем увидеть что-то вроде:

```text
GNU Make 4.4.1
Built for Windows32
```

---

## 1. Первый запуск проекта

### 1.1. Клонирование репозитория и виртуальное окружение

```powershell
cd D:\Documents\JetBrainsIDEProjects\PyCharmProjects

git clone https://github.com/glinozem/wine-assistant.git
cd .\wine-assistant

python -m venv .venv
.\.venv\Scripts\activate

pip install -r requirements.txt
```

Дальше предполагается, что все команды выполняются из корня репозитория
с активированным виртуальным окружением `.venv`.

---

## 2. Работа с Docker через make

В `Makefile` есть несколько удобных целей для управления контейнерами.

### 2.1. Полная пересборка окружения (db + migrator + api + adminer)

Это «жёсткая кнопка Reset» для контейнеров и данных БД:

```powershell
make db-reset
```

Под капотом выполняется:

- `docker compose down -v` — останавливает контейнеры и удаляет volume с данными Postgres;
- `docker compose up -d` — поднимает весь стек (`db`, `migrator`, `api`, `adminer`).

Проверить статус контейнеров можно командой:

```powershell
docker compose ps
```

Ожидаемые статусы:

- `wine-assistant-db` — `Up (...healthy)`
- `wine-assistant-api` — `Up (...healthy)`
- `wine-assistant-adminer` — `Up`
- `wine-assistant-migrator` — отработал и вышел (`exited (0)`) или исчез (one-shot сервис).

### 2.2. Быстрый запуск / остановка только db + api

Если не нужно пересоздавать volume, а просто поднять или остановить сервисы:

```powershell
# поднять только db + api
make dev-up

# остановить всё
make dev-down

# следить за логами api и db
make dev-logs
```

---

## 3. Загрузка прайс-листов в БД (через make)

Сырые прайсы лежат в каталоге:

```text
data\inbox\*.xlsx
```

В стабильном сценарии, который приводит к зелёным тестам,
мы загружаем такие файлы (без «Копия 2025_01_20 …»):

- `data\inbox\2025_06_03 Прайс_Легенда_Виноделия.xlsx`
- `data\inbox\2025_06_25 Прайс_Легенда_Виноделия.xlsx`
- `data\inbox\2025_08_06 Прайс_Легенда_Виноделия.xlsx`
- `data\inbox\2025_08_19 Прайс_Легенда_Виноделия.xlsx`
- `data\inbox\2025_09_29 Прайс_Легенда_Виноделия.xlsx`
- `data\inbox\2025_10_22 Прайс_Легенда_Виноделия.xlsx`
- `data\inbox\2025_10_27 Прайс_Легенда_Виноделия.xlsx`

### 3.1. Цель `load-price`

В `Makefile` есть цель:

```make
load-price:
	python -m scripts.load_csv --excel "$(EXCEL_PATH)"
```

Используем её так (относительные пути — от корня репо):

```powershell
make load-price EXCEL_PATH=".\data\inbox5_06_03 Прайс_Легенда_Виноделия.xlsx"
make load-price EXCEL_PATH=".\data\inbox5_06_25 Прайс_Легенда_Виноделия.xlsx"
make load-price EXCEL_PATH=".\data\inbox5_08_06 Прайс_Легенда_Виноделия.xlsx"
make load-price EXCEL_PATH=".\data\inbox5_08_19 Прайс_Легенда_Виноделия.xlsx"
make load-price EXCEL_PATH=".\data\inbox5_09_29 Прайс_Легенда_Виноделия.xlsx"
make load-price EXCEL_PATH=".\data\inbox5_10_22 Прайс_Легенда_Виноделия.xlsx"
make load-price EXCEL_PATH=".\data\inbox5_10_27 Прайс_Легенда_Виноделия.xlsx"
```

Если всё хорошо, логи `load_csv` для каждого файла заканчиваются так:

```text
[OK] Import completed successfully
   Envelope ID: <uuid>
   Rows processed (good): NNN
   Rows failed (quarantine): 0
   Effective date: YYYY-MM-DD
```

### 3.2. Особый случай: «Копия 2025_01_20 …»

Файл `Копия 2025_01_20 Прайс_Легенда_Виноделия.xlsx` при загрузке **после**
прайсов июня–октября может давать ошибку:

```text
psycopg2.errors.DataException: range lower bound must be less than or equal to range upper bound
```

Это связано с историей цен и диапазонами дат в функции `upsert_price`.

Для текущей тестовой конфигурации этот файл **не обязателен**, поэтому в
стабильном сценарии его просто **не загружаем**.

Если когда-нибудь понадобится полная история с января:

- либо загружать этот файл **первым** (до всех более новых дат),
- либо доработать логику `upsert_price` / диапазоны цен.

---

## 4. Карантин прайс-листа: `price_list_quarantine`

Таблица для проблемных строк прайс-листа — `price_list_quarantine`.

В `Makefile` есть цель:

```make
show-quarantine:
	psql "host=$(DB_HOST) port=$(DB_PORT) user=$(PGUSER) password=$(PGPASSWORD) dbname=$(PGDATABASE)" -c "SELECT id, envelope_id, code, dq_errors, created_at FROM price_list_quarantine ORDER BY created_at DESC LIMIT 50;"
```

Запускаем:

```powershell
make show-quarantine
```

Если все прайсы загрузились «чисто», увидим:

```text
 id | envelope_id | code | dq_errors | created_at
----+-------------+------+-----------+------------
(0 rows)
```

Если какие-то строки попали в карантин, здесь будет видно:

- `code` — код товара,
- `dq_errors` — описание проблем,
- `envelope_id` / `created_at` — отсылка к конкретной загрузке.

---

## 5. Тесты и линтер через make

### 5.1. Юнит-тесты

```powershell
make test-unit
```

Под капотом это просто:

```make
test-unit:
	pytest tests/unit -q
```

Ожидаемый результат: все 100+ тестов `passed`.

### 5.2. Интеграционные тесты с БД

В `Makefile` настроена кросс-платформенная переменная `SET_DBTEST_ENV`,
которая на Windows превращается в `set RUN_DB_TESTS=1 && ...`.

Цели выглядят примерно так:

```make
test-int:
	$(SET_DBTEST_ENV) pytest -m "integration" -vv

test-int-noslow:
	$(SET_DBTEST_ENV) pytest -m "integration and not slow" -vv

test-db: test-int
```

Поэтому запускаем интеграционные тесты так:

```powershell
make test-db
```

или, если нужно без медленных:

```powershell
make test-int-noslow
```

В успешном прогоне было:

```text
============================= 18 passed, 134 deselected in 118.79s =============================
```

### 5.3. Полный прогон + линтер одной командой

Цель `check` делает сразу две вещи:

1. `ruff check .` — статический анализ кода;
2. `pytest -q` — полный прогон всех тестов (API + unit + integration).

```make
check: lint test
	@echo "✅ Линтер и тесты прошли"
```

Запускаем:

```powershell
make check
```

В идеале увидим:

- `All checks passed!` от `ruff`,
- `152 passed` от `pytest -q`,
- и финальное сообщение `"✅ Линтер и тесты прошли"`.

Это и есть состояние «всё зелёное».

---

## 6. Быстрый сценарий «с нуля до зелёных тестов»

Собираем всё вместе для Windows + PowerShell + make.

```powershell
cd D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine-assistant
.\.venv\Scriptsctivate

# 1. Полностью пересоздать docker-окружение
make db-reset

# 2. Загрузить прайс-листы (без проблемной копии 2025-01-20)
make load-price EXCEL_PATH=".\data\inbox5_06_03 Прайс_Легенда_Виноделия.xlsx"
make load-price EXCEL_PATH=".\data\inbox5_06_25 Прайс_Легенда_Виноделия.xlsx"
make load-price EXCEL_PATH=".\data\inbox5_08_06 Прайс_Легенда_Виноделия.xlsx"
make load-price EXCEL_PATH=".\data\inbox5_08_19 Прайс_Легенда_Виноделия.xlsx"
make load-price EXCEL_PATH=".\data\inbox5_09_29 Прайс_Легенда_Виноделия.xlsx"
make load-price EXCEL_PATH=".\data\inbox5_10_22 Прайс_Легенда_Виноделия.xlsx"
make load-price EXCEL_PATH=".\data\inbox5_10_27 Прайс_Легенда_Виноделия.xlsx"

# 3. Проверка карантина (опционально — убедиться, что пусто)
make show-quarantine

# 4. Юнит-тесты (опционально, если хочется отдельно)
make test-unit

# 5. Полный прогон: линтер + все тесты
make check
```

Если все шаги проходят без ошибок, в конце получаем:

- чистый карантин `price_list_quarantine`,
- `ruff` без предупреждений,
- `pytest` с `152 passed`,
- и сообщение `✅ Линтер и тесты прошли`.

Это каноническое состояние «разработка на Windows работает, всё зелёное».
