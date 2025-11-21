# Roadmap: Sprint 7+ (Интеграция винного бизнеса)

**Версия:** 1.0
**Дата создания:** 31 октября 2025
**Статус:** Draft (черновик)
**Автор:** Команда wine-assistant

---

## 🎯 Введение

### Для чего этот документ?

Этот roadmap описывает будущие шаги развития проекта **wine-assistant** после завершения Sprint 4-6 (тесты, логи, метрики).

**Зачем он нужен:**

- 🧠 **Сохранить идеи и контекст** обсуждений
- 📋 **Подготовиться к интеграции** с реальным винным бизнесом
- ⏰ **Понять объём работы** и приоритеты
- 👥 **Коммуникация с командой** (если появится)

**Важно:** Этот план **НЕ отменяет** текущие Sprint 4-6! Мы начнём реализацию только после их завершения.

---

## 📍 Текущее состояние (октябрь 2025)

### Что уже работает ✅

**Технологический стек:**
- Flask API + PostgreSQL (pg_trgm, pgvector)
- Docker Compose для разработки
- GitHub Actions (CI/CD)

**Функционал:**
- 📦 Каталог продуктов (products, product_prices, inventory)
- 📈 История цен и остатков (битемпоральная архитектура)
- 🔍 Поисковый API (/search, /catalog/search)
- 🏥 Healthchecks (/live, /ready, /version)
- 🛡️ Rate limiting (100 req/hour публичные, 1000 req/hour защищённые)
- 📚 Swagger UI документация (/docs)
- 🔒 CORS configuration для фронтенда

**Инфраструктура:**
- ETL: scripts/load_csv.py (Excel/CSV → БД)
- Миграции: SQL-скрипты в db/migrations/
- Тесты: pytest (покрытие 26.69%, цель 60-80%)
- Docker: healthchecks, auto-restart, non-root user

### Текущие спринты (в работе) 🚧

**Sprint 4 — Testing & Quality:**
- #58: Unit-тесты ETL (load_csv.py)
- #59: Integration-тесты API
- #60: E2E сценарии (полные workflows)
- #61: Performance-тесты (load testing)

**Sprint 5 — Observability & Refactoring:**
- #62: Structured JSON logging + request tracing
- #63: Prometheus + Grafana метрики
- #64: Sentry интеграция (error tracking)
- #65: Консолидация ETL (удалить run_daily.py)
- #66: Примеры клиентов (Python/JS)

**Sprint 6 — User Features:**
- #67: Telegram-бот для поиска вин
- #68: Векторный поиск (pgvector + embeddings)
- #69: Export функциональность (Excel/PDF/JSON)

**Цель Sprint 4-6:**
- ✅ Покрытие тестами: 26% → 60-80%
- ✅ Наблюдаемость: structured logs, metrics, alerts
- ✅ UX: боты, экспорт, векторный поиск

---

## 🔮 Видение (куда движемся)

### Бизнес-контекст

Компания **"Виноторг+"** (условное название) занимается:

- 🛒 **Ритейл:** Магазины + онлайн-продажи
- 🍷 **Опт (HoReCa):** Поставки в рестораны, бары, отели
- 🎉 **Дегустации:** Винный бар, мастер-классы, ужины с виноделами

**Текущая проблема:**
- Прайс-листы приходят ежедневно по будням (email-вложения Excel)
- Нет единой системы: Excel, мессенджеры, блокноты
- Теряются заявки, путаются партии и скидки
- Сложно контролировать остатки и маржинальность

**Решение:** Wine Assistant становится центральной системой для:
- ✅ Автоматического импорта прайсов (каждое утро в 08:10)
- ✅ Хранения каталога с историей цен/остатков
- ✅ API для сайта, ботов, интеграций (1С, CRM)
- ✅ Аналитики (маржа, оборачиваемость, dead stock)

### Входные данные (что получаем)

#### 1. Ежедневный прайс-лист (Excel):

**Источник:** Email-вложения от поставщика DW
**Периодичность:** Будни (пн-пт)
**Формат:** Листы "Основной", "Кег", "Крепкий алкоголь", "остатки"
**Содержание:**
- SKU (код товара)
- Наименование, производитель, страна, регион, сорт
- Цена прайс + Цена со скидкой
- Остатки (общий, резерв, свободный)
- Дата прайса (в шапке над блоком "остатки")

#### 2. PDF-каталог (мастер-данные):

**Источник:** Ежеквартальный каталог DW
**Содержание:**
- Производители (сайт, страна/регион, площадь виноградников, энолог)
- Апелласьоны/регионы (иерархия: страна → регион → апелласьон)
- Сорта винограда и купажи
- Рейтинги, медали, дегустационные ноты

### Целевая архитектура

```
Источники                     Wine Assistant                   Потребители
━━━━━━━━━                     ━━━━━━━━━━━━━━                   ━━━━━━━━━━━
📧 Email/Telegram              🗄️ Core System                   🌐 API Clients
     │                               │                              │
     ├─> [Inbox Monitor]  ─────>  [ETL Pipeline]  ─────────>  [REST API]
     │        │                     │       │                      │
     │        ├─ IMAP/Gmail         ├─ Parse Excel                ├─ Сайт
     │        ├─ Telegram           ├─ Validate (DQ)              ├─ Telegram-бот
     │        └─ Папка inbox        ├─ Normalize                  ├─ 1С/CRM
     │                               └─ PostgreSQL                 └─ BI/Grafana
     │
     └─> [PDF Catalog]  ─────────> [Master Data]
              (мастер-данные)        (producers, regions, grapes)
```

**Ключевые принципы:**
- ✅ **Идемпотентность:** Повторная загрузка файла не создаёт дубли
- ✅ **Историчность:** Каждый прайс — снимок на дату (битемпоральность)
- ✅ **Качество данных:** Валидация перед записью, карантин битых файлов
- ✅ **Наблюдаемость:** Structured logs, метрики, алерты при сбоях

---

## 📅 Sprint 7-9 (Детальный план)

### **Sprint 7: Idempotent Import + Business Integration**

**Цель:** Надёжный ежедневный импорт без дублей, правильные даты.
**Длительность:** 2 недели
**Приоритет:** Must-have (критично)

---

#### Issue #77: Идемпотентная загрузка прайсов

**Описание:**
Добавить механизм проверки "Этот файл уже загружен?" по SHA256-хэшу файла.

**Проблема:**
Сейчас повторная загрузка одного файла создаёт дубли в истории цен → неверная аналитика.

**Решение:**

1. **Новая таблица `price_list` (журнал источников):**

```sql
create table price_list(
  id serial primary key,
  supplier_id int not null references supplier(id),
  price_date date not null,              -- дата прайса (из файла)
  source_filename text not null,         -- "Прайс_DW_2025_01_20.xlsx"
  source_file_hash text not null,        -- SHA256 хэш файла
  created_at timestamptz default now(),  -- когда импортировали
  unique (supplier_id, price_date, source_file_hash)
);
```

**Как работает (аналогия):**
Журнал доставки посылок:
- `source_filename` — название посылки
- `source_file_hash` — уникальный номер отслеживания
- Посылка с таким номером уже пришла? → не принимаем повторно

2. **Алгоритм импорта:**

```python
import hashlib

def calculate_sha256(file_path):
    """Вычислить SHA256 хэш файла."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def import_price_list(file_path):
    # 1. Вычисляем хэш
    file_hash = calculate_sha256(file_path)

    # 2. Проверяем в БД
    existing = db.query(
        "SELECT id FROM price_list WHERE source_file_hash = %s",
        (file_hash,)
    )

    if existing:
        logger.info("File already imported, skipping",
                   filename=file_path.name,
                   hash=file_hash[:8])
        return  # Выходим, ничего не делаем

    # 3. Импортируем как обычно
    data = parse_excel(file_path)
    price_date = extract_price_date(data)
    supplier_id = get_supplier_id()

    insert_products(data)
    insert_prices(data, price_date)
    insert_inventory(data, price_date)

    # 4. Записываем в журнал
    db.execute(
        "INSERT INTO price_list(supplier_id, price_date, source_filename, source_file_hash) "
        "VALUES (%s, %s, %s, %s)",
        (supplier_id, price_date, file_path.name, file_hash)
    )

    logger.info("Import successful",
               filename=file_path.name,
               rows=len(data),
               date=price_date)
```

**Чеклист:**
- [ ] Миграция `db/migrations/2025-11-sprint7-price-list.sql` создана
- [ ] Функция `calculate_sha256()` реализована и протестирована
- [ ] Проверка hash перед импортом работает
- [ ] Лог содержит сообщение "Already imported" с хэшем
- [ ] Тест: загрузить файл 3 раза → в БД 1 запись `price_list`

**Критерии готовности (DoD):**
- ✅ Повторная загрузка → 0 дублей в `product_prices`
- ✅ Тест проходит в CI
- ✅ Документация обновлена в README

**Приоритет:** P0 (critical)
**Оценка:** 5 SP
**Связанные issue:** #78, #79

---

#### Issue #78: Извлечение даты прайса из файла

**Описание:**
Брать дату прайса из **самого файла** (шапка Excel), а не из времени импорта.

**Проблема:**
Сейчас, если загрузить прайс за 20 января вечером 21-го, в истории будет дата 21-го (неправильно!).

**Решение:**

1. **Парсинг даты из шапки Excel:**

В файле DW дата находится над блоком "остатки":
```
┌─────────────────────────┐
│ остатки                 │
│ 1/20/2025              │  ← Вот эта дата!
├──────────┬──────────────┤
│ Код      │ Остаток     │
│ D011283  │ 48          │
└──────────┴──────────────┘
```

**Код (с fallback-цепочкой):**

```python
from datetime import datetime, date
import re
import openpyxl

def extract_price_date(excel_path, sheet="Основной"):
    """
    Извлечь дату прайса с fallback-цепочкой:
    1. Из шапки Excel (над "остатки")
    2. Из имени файла (regex)
    3. Из mtime файла
    """

    # Попытка 1: Дата из ячейки Excel
    try:
        wb = openpyxl.load_workbook(excel_path, data_only=True, read_only=True)
        ws = wb[sheet]

        # Ищем ячейку с датой в первых 30 строках
        for row in range(1, 30):
            for col in range(1, 20):
                cell = ws.cell(row, col)

                # Проверяем, это дата?
                if isinstance(cell.value, datetime):
                    price_date = cell.value.date()
                    logger.info("Price date from Excel header", date=price_date)
                    return price_date

        wb.close()
    except Exception as e:
        logger.warning("Failed to extract date from Excel", error=str(e))

    # Попытка 2: Дата из имени файла
    # Примеры: "Прайс_2025_01_20.xlsx", "DW_2025-01-20.xlsx"
    match = re.search(r'(\d{4})[_-](\d{2})[_-](\d{2})', excel_path.name)
    if match:
        price_date = date(int(match[1]), int(match[2]), int(match[3]))
        logger.info("Price date from filename", date=price_date)
        return price_date

    # Попытка 3: mtime файла (последний resort)
    mtime = excel_path.stat().st_mtime
    price_date = datetime.fromtimestamp(mtime).date()
    logger.warning("Price date from file mtime (fallback)", date=price_date)
    return price_date

def validate_price_date(price_date):
    """Валидация даты прайса."""
    today = date.today()

    # Не из будущего
    if price_date > today:
        raise ValueError(f"Price date {price_date} is in the future")

    # Не старше 30 дней (настраиваемый порог)
    age_days = (today - price_date).days
    if age_days > 30:
        logger.warning("Price date is old", date=price_date, age_days=age_days)

    return price_date
```

**Интеграция в ETL:**

```python
# scripts/load_csv.py

def main(excel, asof=None):
    # Извлекаем дату прайса
    if asof:
        price_date = datetime.strptime(asof, "%Y-%m-%d").date()
    else:
        price_date = extract_price_date(excel)
        price_date = validate_price_date(price_date)

    # Импортируем с правильной датой
    df = read_any(excel)
    upsert_records(df, price_date)  # Используем price_date, не datetime.now()
```

**Чеклист:**
- [ ] Функция `extract_price_date()` реализована
- [ ] Fallback-цепочка работает (шапка → имя → mtime)
- [ ] Функция `validate_price_date()` проверяет корректность
- [ ] `product_prices.effective_from` берёт эту дату
- [ ] `inventory_history.as_of` берёт эту дату
- [ ] Тесты:
  - [ ] Файл "Прайс_2025_01_20.xlsx" → price_date = 2025-01-20
  - [ ] Дата из шапки приоритетнее имени файла
  - [ ] Валидация отклоняет будущие даты

**Критерии готовности (DoD):**
- ✅ История цен привязана к дате прайса (не импорта)
- ✅ Тесты проходят для всех 3 fallback-сценариев
- ✅ Лог содержит информацию об источнике даты

**Приоритет:** P0 (critical)
**Оценка:** 3 SP
**Связанные issue:** #77

---

#### Issue #79: Планировщик ежедневных обновлений (будни)

**Описание:**
Автоматический запуск импорта каждый будний день в 08:10 (пн-пт).

**Решение:**

1. **Джоб-скрипт для автоматического импорта:**

```python
# jobs/ingest_dw_price.py
"""
Ежедневный импорт прайс-листов DW.
Запускается cron/systemd: пн-пт 08:10 Europe/Helsinki
"""
import sys
import logging
from pathlib import Path
from datetime import datetime
from scripts.load_csv import main as load_csv_main

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('logs/import.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def process_file(file_path):
    """Обработать один файл."""
    try:
        logger.info(f"Processing {file_path.name}...")

        # Импорт через основной скрипт
        load_csv_main(excel=str(file_path), asof=None)

        # Архивируем файл после успешной загрузки
        archive_dir = Path("data/archive") / datetime.now().strftime("%Y-%m-%d")
        archive_dir.mkdir(parents=True, exist_ok=True)

        archived_path = archive_dir / file_path.name
        file_path.rename(archived_path)

        logger.info(f"✅ Success: {file_path.name} → {archived_path}")
        return True

    except Exception as e:
        logger.error(f"❌ Error processing {file_path.name}: {e}", exc_info=True)
        # Файл остаётся в inbox для повторной обработки
        return False

def run_daily_import():
    """Главная функция: обработка всех файлов из inbox."""
    inbox = Path("data/inbox")

    if not inbox.exists():
        logger.warning(f"Inbox directory does not exist: {inbox}")
        return

    # Находим все Excel-файлы с "прайс" в названии
    files = sorted(inbox.glob("*прайс*.xlsx"))

    if not files:
        logger.info("No new price files in inbox")
        return

    logger.info(f"Found {len(files)} file(s) to process")

    success_count = 0
    error_count = 0

    for file_path in files:
        if process_file(file_path):
            success_count += 1
        else:
            error_count += 1

    # Итоговая статистика
    logger.info(f"Import completed: {success_count} success, {error_count} errors")

    # Алерт при ошибках
    if error_count > 0:
        send_alert(f"Import errors: {error_count} files failed")

def send_alert(message):
    """Отправить алерт при ошибке (email/Slack/Sentry)."""
    # TODO: интеграция с Sentry/email/Slack
    logger.critical(f"ALERT: {message}")

if __name__ == "__main__":
    logger.info("=== Starting daily import job ===")
    run_daily_import()
    logger.info("=== Daily import job finished ===")
```

2. **Настройка cron (Linux/Mac):**

```bash
# Открываем редактор cron
crontab -e

# Добавляем строку (08:10 пн-пт, таймзона Europe/Helsinki)
# Минута Час День Месяц ДеньНедели Команда
10 8 * * 1-5 cd /path/to/wine-assistant && /usr/bin/python jobs/ingest_dw_price.py >> logs/cron.log 2>&1
```

**Объяснение cron-строки:**
```
10 8 * * 1-5
│  │ │ │ └─── дни недели (1-5 = пн-пт)
│  │ │ └───── месяц (* = любой)
│  │ └─────── день месяца (* = любой)
│  └───────── час (8 = 08:00)
└─────────── минута (10 = :10)
```

3. **Альтернатива: systemd timer (современный подход):**

```ini
# /etc/systemd/system/wine-assistant-import.service
[Unit]
Description=Wine Assistant Daily Import
After=network.target

[Service]
Type=oneshot
User=wine-assistant
WorkingDirectory=/opt/wine-assistant
ExecStart=/usr/bin/python /opt/wine-assistant/jobs/ingest_dw_price.py
StandardOutput=append:/opt/wine-assistant/logs/import.log
StandardError=append:/opt/wine-assistant/logs/import.log

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/wine-assistant-import.timer
[Unit]
Description=Wine Assistant Daily Import Timer
Requires=wine-assistant-import.service

[Timer]
OnCalendar=Mon-Fri 08:10:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
# Активация systemd timer
sudo systemctl enable wine-assistant-import.timer
sudo systemctl start wine-assistant-import.timer

# Проверка статуса
sudo systemctl status wine-assistant-import.timer
sudo systemctl list-timers --all | grep wine-assistant
```

4. **Альтернатива для Windows (Task Scheduler):**

```powershell
# Создать задачу через PowerShell
$action = New-ScheduledTaskAction `
    -Execute "python.exe" `
    -Argument "C:\wine-assistant\jobs\ingest_dw_price.py" `
    -WorkingDirectory "C:\wine-assistant"

$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At 08:10

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName "WineAssistant-DailyImport" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User "SYSTEM" `
    -RunLevel Highest
```

**Чеклист:**
- [ ] Скрипт `jobs/ingest_dw_price.py` создан и протестирован
- [ ] Логирование в файл + консоль работает
- [ ] Архивирование успешных файлов работает
- [ ] Cron/systemd/Task Scheduler настроен
- [ ] Тест: запустить вручную → файлы обработаны
- [ ] Алерт при сбое (email/Slack/Sentry)
- [ ] Документация в README: "Как настроить автоимпорт"

**Критерии готовности (DoD):**
- ✅ Импорт срабатывает автоматически по будням
- ✅ При ошибке → уведомление
- ✅ Лог содержит timestamp, файлы, результаты
- ✅ Успешные файлы перенесены в archive/

**Приоритет:** P1 (high)
**Оценка:** 5 SP
**Связанные issue:** #80

---

#### Issue #80: Автоматический приём вложений (email/inbox)

**Описание:**
Скачивать прайсы из почты/мессенджера в папку `data/inbox` автоматически.

**Зачем:**
Полная автоматизация цепочки: прайс приходит на почту → скачивается → импортируется.

**Решение:**

**Вариант 1: IMAP-downloader (Gmail/Yandex):**

```python
# scripts/fetch_email_attachments.py
"""
Скачивание вложений из email (IMAP).
Запускается за 5 минут до основного импорта (08:05).
"""
import imaplib
import email
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройки (из переменных окружения)
IMAP_SERVER = "imap.gmail.com"  # или imap.yandex.ru
EMAIL_USER = "your-email@gmail.com"
EMAIL_PASSWORD = "your-app-password"  # НЕ обычный пароль!

INBOX_DIR = Path("data/inbox")
INBOX_DIR.mkdir(parents=True, exist_ok=True)

def connect_to_email():
    """Подключиться к почтовому серверу."""
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_USER, EMAIL_PASSWORD)
    return mail

def download_attachments():
    """Скачать вложения из непрочитанных писем."""
    mail = connect_to_email()
    mail.select("INBOX")

    # Ищем непрочитанные письма с темой "прайс"
    status, messages = mail.search(None, '(UNSEEN SUBJECT "прайс")')

    if status != "OK":
        logger.warning("Failed to search emails")
        return

    message_ids = messages[0].split()
    logger.info(f"Found {len(message_ids)} unread email(s)")

    downloaded_count = 0

    for msg_id in message_ids:
        status, msg_data = mail.fetch(msg_id, "(RFC822)")

        for response_part in msg_data:
            if not isinstance(response_part, tuple):
                continue

            msg = email.message_from_bytes(response_part[1])

            # Метаданные письма
            sender = msg.get("From")
            subject = msg.get("Subject")
            date_str = msg.get("Date")

            logger.info(f"Processing email: {subject} from {sender}")

            # Извлекаем вложения
            for part in msg.walk():
                if part.get_content_disposition() != "attachment":
                    continue

                filename = part.get_filename()

                # Фильтруем только Excel
                if not filename or not filename.endswith((".xlsx", ".xls")):
                    continue

                # Сохраняем файл
                filepath = INBOX_DIR / filename

                # Если файл уже есть — добавляем timestamp
                if filepath.exists():
                    stem = filepath.stem
                    suffix = filepath.suffix
                    timestamp = datetime.now().strftime("%H%M%S")
                    filepath = INBOX_DIR / f"{stem}_{timestamp}{suffix}"

                filepath.write_bytes(part.get_payload(decode=True))

                logger.info(f"✅ Downloaded: {filename} ({filepath.stat().st_size} bytes)")
                downloaded_count += 1

            # Помечаем письмо как прочитанное
            mail.store(msg_id, "+FLAGS", "\\Seen")

    mail.logout()
    logger.info(f"Total downloaded: {downloaded_count} file(s)")

if __name__ == "__main__":
    logger.info("=== Fetching email attachments ===")
    download_attachments()
    logger.info("=== Fetch completed ===")
```

**Настройка Gmail App Password:**

1. Зайти: https://myaccount.google.com/security
2. Включить 2-Step Verification
3. Создать App Password для "Mail" → скопировать 16-символьный пароль
4. Использовать этот пароль в `EMAIL_PASSWORD` (НЕ обычный пароль!)

**Настройка cron (за 5 минут до импорта):**
```bash
# 08:05 пн-пт
5 8 * * 1-5 cd /path/to/wine-assistant && /usr/bin/python scripts/fetch_email_attachments.py >> logs/fetch.log 2>&1
```

**Вариант 2: Telegram-бот (опционально):**

```python
# scripts/telegram_receiver.py
"""
Принимать прайсы через Telegram-бот.
"""
from telegram.ext import Updater, MessageHandler, Filters
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "YOUR_BOT_TOKEN"
INBOX_DIR = Path("data/inbox")

def handle_document(update, context):
    """Обработчик загрузки документа."""
    document = update.message.document

    # Проверяем расширение
    if not document.file_name.endswith((".xlsx", ".xls")):
        update.message.reply_text("❌ Пожалуйста, отправьте Excel-файл (.xlsx)")
        return

    # Скачиваем файл
    file = context.bot.get_file(document.file_id)
    filepath = INBOX_DIR / document.file_name
    file.download(str(filepath))

    logger.info(f"✅ Received file: {document.file_name}")
    update.message.reply_text(f"✅ Файл получен: {document.file_name}\nИмпорт будет выполнен в 08:10")

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Обработчик документов
    dp.add_handler(MessageHandler(Filters.document, handle_document))

    logger.info("Telegram bot started")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
```

**Чеклист:**
- [ ] Скрипт `fetch_email_attachments.py` работает
- [ ] Gmail/Yandex App Password настроен
- [ ] Тест: отправить себе тестовое письмо с вложением → файл скачан в inbox
- [ ] Метаданные сохраняются (отправитель, тема, дата)
- [ ] Cron настроен на 08:05
- [ ] (Опционально) Telegram-бот работает
- [ ] Документация в README: "Как настроить email-интеграцию"

**Критерии готовности (DoD):**
- ✅ Прайсы автоматически попадают в `data/inbox`
- ✅ Метаданные доступны для аудита
- ✅ Тест: отправка → скачивание → импорт (E2E)

**Приоритет:** P2 (medium)
**Оценка:** 8 SP
**Связанные issue:** #79

---

### **Sprint 8: Business Data Model**

**Цель:** Обогатить каталог мастер-данными из PDF-каталога, поддержать кеги/розлив.
**Длительность:** 2 недели
**Приоритет:** Should-have (важно)

---

#### Issue #81: Мастер-данные из PDF-каталога DW

**Описание:**
Импортировать справочники из PDF-каталога: производители, регионы, апелласьоны, сорта винограда.

**Зачем это нужно:**
Сейчас в БД только цены и остатки. Для хорошего каталога нужны:

- 🏭 Производители: название, сайт, страна, энолог, площадь виноградников
- 🌍 География: страна → регион → апелласьон (Франция → Бордо → Médoc AOC)
- 🍇 Купажи: Каберне 60% + Мерло 40%
- ⭐ Рейтинги: Vivino, Decanter, Parker

**Решение:**

1. **Новые таблицы (миграция):**

```sql
-- db/migrations/2025-11-sprint8-master-data.sql

-- Производители
create table if not exists producers(
  id serial primary key,
  name text unique not null,
  website text,
  country text,
  region text,
  vineyard_ha numeric(8,2),        -- площадь виноградников (га)
  winemaker text,                  -- энолог
  founded_year int,
  description text                 -- из PDF-каталога
);

-- Регионы (иерархия)
create table if not exists regions(
  id serial primary key,
  name text unique not null,
  country text not null,
  parent_region_id int references regions(id),  -- Бордо → Франция
  description text
);

-- Апелласьоны (AOC/DOC/IGP/DOCG)
create table if not exists appellations(
  id serial primary key,
  name text unique not null,
  region_id int references regions(id),
  type text not null,              -- AOC, IGP, DOC, DOCG, AVA, и т.д.
  description text
);

-- Сорта винограда
create table if not exists grapes(
  id serial primary key,
  name text unique not null,
  type text,                       -- red, white, rosé
  description text
);

-- Купажи (многие-ко-многим)
create table if not exists product_grape_blend(
  product_id int references products(id) on delete cascade,
  grape_id int references grapes(id),
  percentage numeric(5,2),         -- доля в купаже (60.00 = 60%)
  primary key(product_id, grape_id)
);

-- Расширяем таблицу products
alter table products
  add column if not exists producer_id int references producers(id),
  add column if not exists appellation_id int references appellations(id),
  add column if not exists vivino_url text,
  add column if not exists rating_vivino numeric(3,1),   -- 4.2
  add column if not exists rating_parker int,           -- 95
  add column if not exists certificate text;            -- AOC, AOP, IGP

-- Индексы для производительности
create index if not exists idx_products_producer on products(producer_id);
create index if not exists idx_products_appellation on products(appellation_id);
create index if not exists idx_products_rating on products(rating_vivino desc nulls last);
create index if not exists idx_regions_country on regions(country);
create index if not exists idx_appellations_region on appellations(region_id);
```

2. **Парсер PDF-каталога:**

```python
# scripts/parse_pdf_catalog.py
"""
Извлечение мастер-данных из PDF-каталога DW.
"""
import pdfplumber
import re
import logging
from typing import List, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_producers(pdf_path) -> List[Dict]:
    """
    Извлечь информацию о производителях.

    Ожидаемый формат секции "ПРОИЗВОДИТЕЛИ":
    Название | Страна | Регион | Сайт | Площадь (га) | Энолог
    """
    producers = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()

            # Ищем секцию "ПРОИЗВОДИТЕЛИ" или "PRODUCERS"
            if not ("ПРОИЗВОДИТЕЛИ" in text or "PRODUCERS" in text):
                continue

            logger.info(f"Found producers section on page {page.page_number}")

            # Парсим таблицу
            tables = page.extract_tables()
            for table in tables:
                for row in table[1:]:  # Пропускаем заголовок
                    if len(row) < 6:
                        continue

                    try:
                        producers.append({
                            "name": row[0].strip(),
                            "country": row[1].strip(),
                            "region": row[2].strip(),
                            "website": row[3].strip() if row[3] else None,
                            "vineyard_ha": float(row[4]) if row[4] else None,
                            "winemaker": row[5].strip() if row[5] else None
                        })
                    except Exception as e:
                        logger.warning(f"Failed to parse producer row: {row}, error: {e}")

    logger.info(f"Extracted {len(producers)} producers")
    return producers

def extract_regions(pdf_path) -> List[Dict]:
    """
    Извлечь иерархию регионов.

    Ожидаемый формат: Страна → Регион → Субрегион
    """
    regions = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()

            # Ищем секцию "РЕГИОНЫ" или "REGIONS"
            if not ("РЕГИОНЫ" in text or "REGIONS" in text):
                continue

            logger.info(f"Found regions section on page {page.page_number}")

            # Парсим иерархию (примерная логика)
            lines = text.split("\n")
            current_country = None
            current_region = None

            for line in lines:
                # Страна (заглавными)
                if line.isupper() and len(line.split()) <= 3:
                    current_country = line.strip()
                    regions.append({
                        "name": current_country,
                        "country": current_country,
                        "parent": None
                    })
                # Регион (с отступом)
                elif line.startswith("  ") and current_country:
                    region_name = line.strip()
                    regions.append({
                        "name": region_name,
                        "country": current_country,
                        "parent": current_country
                    })
                    current_region = region_name
                # Субрегион (с большим отступом)
                elif line.startswith("    ") and current_region:
                    subregion_name = line.strip()
                    regions.append({
                        "name": subregion_name,
                        "country": current_country,
                        "parent": current_region
                    })

    logger.info(f"Extracted {len(regions)} regions")
    return regions

def extract_appellations(pdf_path) -> List[Dict]:
    """Извлечь апелласьоны (AOC/DOC/IGP)."""
    appellations = []

    # Парсинг секции "АПЕЛЛАСЬОНЫ"
    # Формат: Название | Регион | Тип (AOC/DOC/IGP)

    # TODO: реализовать логику парсинга

    return appellations

def main(pdf_path):
    """Главная функция импорта мастер-данных."""
    logger.info(f"Parsing PDF catalog: {pdf_path}")

    # Извлекаем данные
    producers = extract_producers(pdf_path)
    regions = extract_regions(pdf_path)
    appellations = extract_appellations(pdf_path)

    # Загружаем в БД
    from db import get_conn

    with get_conn() as conn:
        cur = conn.cursor()

        # Вставка производителей
        for p in producers:
            cur.execute("""
                insert into producers(name, country, region, website, vineyard_ha, winemaker)
                values (%(name)s, %(country)s, %(region)s, %(website)s, %(vineyard_ha)s, %(winemaker)s)
                on conflict (name) do update set
                  country = excluded.country,
                  region = excluded.region,
                  website = excluded.website,
                  vineyard_ha = excluded.vineyard_ha,
                  winemaker = excluded.winemaker
            """, p)

        # Вставка регионов (с учётом иерархии)
        for r in regions:
            parent_id = None
            if r["parent"]:
                cur.execute("select id from regions where name = %s", (r["parent"],))
                result = cur.fetchone()
                parent_id = result[0] if result else None

            cur.execute("""
                insert into regions(name, country, parent_region_id)
                values (%s, %s, %s)
                on conflict (name) do nothing
            """, (r["name"], r["country"], parent_id))

        conn.commit()

    logger.info("✅ Master data import completed")

if __name__ == "__main__":
    main("data/Каталог_DW_2025.pdf")
```

3. **Интеграция с ETL (автоподтяжка при импорте Excel):**

```python
# scripts/load_csv.py

def enrich_product_with_master_data(product_data):
    """
    Подтянуть мастер-данные по SKU.
    """
    sku = product_data["code"]

    # Найти производителя
    producer_name = product_data.get("producer")
    if producer_name:
        producer_id = db.query_one(
            "select id from producers where name ilike %s",
            (producer_name,)
        )
        product_data["producer_id"] = producer_id

    # Найти регион/апелласьон
    region_name = product_data.get("region")
    if region_name:
        appellation_id = db.query_one(
            "select id from appellations where name ilike %s",
            (region_name,)
        )
        product_data["appellation_id"] = appellation_id

    return product_data
```

**Чеклист:**
- [ ] Миграция с новыми таблицами применена
- [ ] Парсер PDF работает (извлекает ≥90% производителей)
- [ ] Скрипт `parse_pdf_catalog.py` загружает данные в БД
- [ ] При импорте Excel автоподтягиваются `producer_id`, `appellation_id`
- [ ] API endpoints:
  - [ ] GET /api/v1/producers
  - [ ] GET /api/v1/regions
  - [ ] GET /api/v1/grapes
  - [ ] GET /api/v1/appellations
- [ ] Swagger документация обновлена
- [ ] Тест: SKU D011283 → автоматически привязан к Fontanafredda (Пьемонт)

**Критерии готовности (DoD):**
- ✅ Справочники заполнены из PDF
- ✅ При импорте Excel мастер-данные подтягиваются автоматически
- ✅ API возвращает обогащённые карточки товаров
- ✅ Покрытие тестами ≥ 70%

**Приоритет:** P1 (high)
**Оценка:** 13 SP
**Связанные issue:** #82

---

#### Issue #82: Поддержка кегов и цен на розлив

**Описание:**
Для HoReCa нужны цены на бокалы (125 мл, 150 мл) и графины (0.75 л, 1 л) из кегов.

**Зачем:**
Винные бары/рестораны покупают кеги 20 л и продают по бокалам → нужна калькуляция себестоимости.

**Решение:**

1. **Таблица `serving_prices`:**

```sql
-- db/migrations/2025-11-sprint8-servings.sql

create table if not exists serving_prices(
  id serial primary key,
  product_id int not null references products(id) on delete cascade,
  size_ml int not null,                -- 125, 150, 750, 1000
  price_rub numeric(12,2) not null,
  price_date date not null,
  unique(product_id, size_ml, price_date)
);

create index if not exists idx_serving_prices_product_date
  on serving_prices(product_id, price_date desc);

-- Опционально: yield для контроля себестоимости
create table if not exists serving_yield(
  product_id int primary key references products(id),
  keg_volume_l numeric(6,2) not null,  -- 20.0
  servings_125ml int,                  -- кол-во бокалов 125 мл из кега
  servings_150ml int,
  loss_pct numeric(5,2) default 5.0    -- потери при розливе (пена, остаток)
);
```

2. **Парсер листа "Кег":**

```python
# scripts/load_csv.py

def parse_keg_sheet(excel_path, price_date):
    """
    Парсить лист "Кег" с ценами на розлив.
    """
    df = pd.read_excel(excel_path, sheet_name="Кег")

    # Нормализация колонок
    df = df.rename(columns={
        "Код": "sku",
        "Наименование": "product_name",
        "цена 125 мл": "price_125ml",
        "цена 150 мл": "price_150ml",
        "цена 0,75 л": "price_750ml",
        "цена 1 л": "price_1l",
        "кол-во бокалов 125 мл": "servings_125ml"
    })

    for _, row in df.iterrows():
        sku = row["sku"]

        # Создать/обновить продукт
        product_id = get_or_create_product({
            "code": sku,
            "title_ru": row["product_name"],
            "pack": "KEG",
            "volume": "20.0"  # кег 20 л
        })

        # Вставить цены на розлив
        servings = [
            (125, row.get("price_125ml")),
            (150, row.get("price_150ml")),
            (750, row.get("price_750ml")),
            (1000, row.get("price_1l"))
        ]

        for size_ml, price in servings:
            if pd.notna(price) and price > 0:
                insert_serving_price(product_id, size_ml, price, price_date)

        # Опционально: yield (кол-во бокалов)
        if pd.notna(row.get("servings_125ml")):
            insert_serving_yield(
                product_id,
                keg_volume_l=20.0,
                servings_125ml=int(row["servings_125ml"])
            )

def insert_serving_price(product_id, size_ml, price_rub, price_date):
    """Вставить/обновить цену на розлив."""
    db.execute("""
        insert into serving_prices(product_id, size_ml, price_rub, price_date)
        values (%s, %s, %s, %s)
        on conflict (product_id, size_ml, price_date) do update set
          price_rub = excluded.price_rub
    """, (product_id, size_ml, price_rub, price_date))
```

3. **API endpoint:**

```python
# api/app.py

@app.route('/api/v1/products/<int:product_id>/servings', methods=['GET'])
def get_servings(product_id):
    """
    Получить цены на розлив.

    GET /api/v1/products/123/servings?date=2025-01-20

    Response:
    {
      "product_id": 123,
      "servings": [
        {"size_ml": 125, "price_rub": 450.00},
        {"size_ml": 150, "price_rub": 520.00},
        {"size_ml": 750, "price_rub": 2100.00},
        {"size_ml": 1000, "price_rub": 2700.00}
      ],
      "yield": {
        "keg_volume_l": 20.0,
        "servings_125ml": 160,
        "loss_pct": 5.0
      }
    }
    """
    date_param = request.args.get('date', date.today())

    # Цены на розлив
    servings = db.query_all("""
        select size_ml, price_rub
        from serving_prices
        where product_id = %s
          and price_date <= %s
        order by price_date desc, size_ml
        limit 10
    """, (product_id, date_param))

    # Yield (опционально)
    yield_info = db.query_one("""
        select keg_volume_l, servings_125ml, servings_150ml, loss_pct
        from serving_yield
        where product_id = %s
    """, (product_id,))

    return jsonify({
        "product_id": product_id,
        "servings": [{"size_ml": s[0], "price_rub": float(s[1])} for s in servings],
        "yield": dict(yield_info) if yield_info else None
    })
```

**Чеклист:**
- [ ] Миграция `serving_prices` и `serving_yield` применена
- [ ] Парсер листа "Кег" работает корректно
- [ ] API `/products/{id}/servings` возвращает данные
- [ ] Swagger документация обновлена (пример запроса/ответа)
- [ ] Тесты:
  - [ ] Кег 20 л → 160 бокалов по 125 мл
  - [ ] Цена 125 мл корректно импортируется
  - [ ] API возвращает актуальные цены на дату

**Критерии готовности (DoD):**
- ✅ Лист "Кег" импортируется без ошибок
- ✅ API `/servings` работает
- ✅ Калькуляция себестоимости бокала доступна

**Приоритет:** P2 (medium)
**Оценка:** 8 SP
**Связанные issue:** #81

---

#### Issue #83: Остатки по локациям (опционально)

**Описание:**
Детализация остатков по складам/магазинам/барам.

**Зачем:**
Для аналитики: сколько вина в каждой точке, оптимизация пополнения.

**Решение:**

```sql
-- db/migrations/2025-11-sprint8-stock-locations.sql

create table if not exists stock_by_location(
  id serial primary key,
  product_id int not null references products(id) on delete cascade,
  location text not null,              -- "Склад_Москва", "Бар_Патриаршие"
  stock_qty numeric(12,3) not null,
  snapshot_date date not null,
  unique(product_id, location, snapshot_date)
);

create index if not exists idx_stock_by_location_product_date
  on stock_by_location(product_id, snapshot_date desc);

create index if not exists idx_stock_by_location_location
  on stock_by_location(location, snapshot_date desc);
```

**Парсер листа "остатки":**
```python
def parse_stock_locations(excel_path, stock_date):
    """
    Парсить лист "остатки" с разбивкой по локациям.

    Ожидаемые колонки:
    Код | ВИНО_Осн_Мск | ВИНО_Осн_СПб | Бар_Патриаршие | ...
    """
    df = pd.read_excel(excel_path, sheet_name="остатки")

    # Первая колонка — код товара, остальные — локации
    locations = df.columns[1:]

    for _, row in df.iterrows():
        sku = row.iloc[0]
        product_id = get_product_id_by_sku(sku)

        if not product_id:
            continue

        # По каждой локации
        for location in locations:
            stock_qty = row[location]

            if pd.notna(stock_qty) and stock_qty > 0:
                db.execute("""
                    insert into stock_by_location(product_id, location, stock_qty, snapshot_date)
                    values (%s, %s, %s, %s)
                    on conflict (product_id, location, snapshot_date) do update set
                      stock_qty = excluded.stock_qty
                """, (product_id, location, stock_qty, stock_date))
```

**API:**
```python
@app.route('/api/v1/stocks', methods=['GET'])
def get_stocks():
    """
    GET /api/v1/stocks?date=2025-01-20&location=Склад_Москва&product_id=123
    """
    date_param = request.args.get('date', date.today())
    location = request.args.get('location')
    product_id = request.args.get('product_id', type=int)

    where = ["snapshot_date = %s"]
    params = [date_param]

    if location:
        where.append("location = %s")
        params.append(location)

    if product_id:
        where.append("product_id = %s")
        params.append(product_id)

    sql = f"""
        select product_id, location, stock_qty, snapshot_date
        from stock_by_location
        where {' and '.join(where)}
        order by location, product_id
    """

    stocks = db.query_all(sql, params)
    return jsonify({"stocks": stocks, "date": date_param})
```

**Чеклист:**
- [ ] Миграция `stock_by_location` применена
- [ ] Парсер листа "остатки" извлекает локации
- [ ] Агрегация в дневной срез `inventory_history` работает
- [ ] API `/stocks` с фильтрами по локации/дате/товару
- [ ] Swagger документация
- [ ] Тест: отчёт по складам корректен

**Критерии готовности (DoD):**
- ✅ Остатки по локациям доступны через API
- ✅ Аналитика: "где сколько лежит"

**Приоритет:** P3 (low / nice-to-have)
**Оценка:** 5 SP

---

### **Sprint 9: API Extensions**

**Цель:** Улучшить поиск и фильтрацию для витрин (сайт/бот).

**Длительность:** 1 неделя
**Приоритет:** Should-have

---

#### Issue #86: GET /products с расширенными фильтрами

**Описание:**
Богатые фильтры для каталога: по стране, региону, сорту, крепости, цене, наличию.

**API спецификация:**
```
GET /api/v1/products
  ?country=Италия
  &region=Тоскана
  &appellation=Brunello_di_Montalcino_DOCG
  &grape=Санджовезе
  &color=Красное
  &style=Сухое
  &abv_min=13.0
  &abv_max=15.0
  &price_min=1000
  &price_max=5000
  &vintage=2018
  &in_stock=true
  &producer=Antinori
  &rating_min=4.0
  &limit=20
  &offset=0
  &sort=price_asc|price_desc|name_asc|rating_desc|newest

Response:
{
  "items": [
    {
      "id": 123,
      "code": "D011283",
      "title_ru": "Фонтанафредда Бароло",
      "producer": "Fontanafredda",
      "country": "Италия",
      "region": "Пьемонт",
      "appellation": "Barolo DOCG",
      "grapes": [
        {"name": "Неббиоло", "percentage": 100}
      ],
      "color": "Красное",
      "style": "Сухое",
      "vintage": 2018,
      "abv_pct": 14.0,
      "volume_l": 0.75,
      "price_list_rub": 4500.00,
      "price_final_rub": 4050.00,
      "rating_vivino": 4.2,
      "in_stock": true,
      "stock_free": 43
    }
  ],
  "total": 150,
  "limit": 20,
  "offset": 0,
  "filters_applied": {
    "country": "Италия",
    "region": "Тоскана",
    "grape": "Санджовезе"
  }
}
```

**Реализация:**
```python
@app.route('/api/v1/products', methods=['GET'])
def get_products_v1():
    """Поиск товаров с расширенными фильтрами."""

    # Параметры пагинации
    limit = request.args.get('limit', default=20, type=int)
    offset = request.args.get('offset', default=0, type=int)

    # Параметры фильтрации
    country = request.args.get('country')
    region = request.args.get('region')
    appellation = request.args.get('appellation')
    grape = request.args.get('grape')
    color = request.args.get('color')
    style = request.args.get('style')
    abv_min = request.args.get('abv_min', type=float)
    abv_max = request.args.get('abv_max', type=float)
    price_min = request.args.get('price_min', type=float)
    price_max = request.args.get('price_max', type=float)
    vintage = request.args.get('vintage', type=int)
    in_stock = request.args.get('in_stock', type=lambda x: x.lower() == 'true')
    producer = request.args.get('producer')
    rating_min = request.args.get('rating_min', type=float)

    # Параметр сортировки
    sort = request.args.get('sort', default='price_asc')

    # Построение SQL-запроса
    where = []
    params = []

    if country:
        where.append("p.country ILIKE %s")
        params.append(f"%{country}%")

    if region:
        where.append("p.region ILIKE %s")
        params.append(f"%{region}%")

    if appellation:
        where.append("a.name ILIKE %s")
        params.append(f"%{appellation}%")

    if grape:
        where.append("""
            exists(
                select 1 from product_grape_blend pgb
                join grapes g on g.id = pgb.grape_id
                where pgb.product_id = p.id and g.name ilike %s
            )
        """)
        params.append(f"%{grape}%")

    if color:
        where.append("p.color ILIKE %s")
        params.append(f"%{color}%")

    if style:
        where.append("p.style ILIKE %s")
        params.append(f"%{style}%")

    if abv_min is not None:
        where.append("p.abv >= %s")
        params.append(abv_min)

    if abv_max is not None:
        where.append("p.abv <= %s")
        params.append(abv_max)

    if price_min is not None:
        where.append("p.price_final_rub >= %s")
        params.append(price_min)

    if price_max is not None:
        where.append("p.price_final_rub <= %s")
        params.append(price_max)

    if vintage:
        where.append("p.vintage = %s")
        params.append(vintage)

    if in_stock:
        where.append("coalesce(i.stock_free, 0) > 0")

    if producer:
        where.append("pr.name ILIKE %s")
        params.append(f"%{producer}%")

    if rating_min:
        where.append("p.rating_vivino >= %s")
        params.append(rating_min)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    # Сортировка
    order_sql = {
        'price_asc': 'p.price_final_rub ASC',
        'price_desc': 'p.price_final_rub DESC',
        'name_asc': 'p.title_ru ASC',
        'rating_desc': 'p.rating_vivino DESC NULLS LAST',
        'newest': 'p.id DESC'
    }.get(sort, 'p.price_final_rub ASC')

    # Основной запрос
    sql = f"""
        select
            p.id, p.code, p.title_ru, p.title_en,
            pr.name as producer,
            p.country, p.region,
            a.name as appellation,
            p.color, p.style, p.vintage, p.abv, p.volume,
            p.price_list_rub, p.price_final_rub,
            p.rating_vivino,
            coalesce(i.stock_free, 0) > 0 as in_stock,
            coalesce(i.stock_free, 0) as stock_free,
            count(*) over() as total_count
        from products p
        left join producers pr on pr.id = p.producer_id
        left join appellations a on a.id = p.appellation_id
        left join inventory i on i.code = p.code
        {where_sql}
        order by {order_sql}
        limit %s offset %s
    """

    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, (*params, limit, offset))
        rows = cur.fetchall()

    total = rows[0]["total_count"] if rows else 0

    # Убираем служебное поле
    for r in rows:
        r.pop("total_count", None)

    # Добавляем информацию о купажах
    for r in rows:
        r["grapes"] = get_product_grapes(r["id"])

    return jsonify({
        "items": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters_applied": {
            k: v for k, v in request.args.items()
            if k not in ('limit', 'offset', 'sort')
        }
    })

def get_product_grapes(product_id):
    """Получить купаж для товара."""
    grapes = db.query_all("""
        select g.name, pgb.percentage
        from product_grape_blend pgb
        join grapes g on g.id = pgb.grape_id
        where pgb.product_id = %s
        order by pgb.percentage desc nulls last
    """, (product_id,))

    return [{"name": g[0], "percentage": float(g[1]) if g[1] else None} for g in grapes]
```

**Чеклист:**
- [ ] Все фильтры работают корректно
- [ ] Пагинация работает
- [ ] Сортировка по всем вариантам работает
- [ ] Индексы для производительности (< 200 мс на 10K товаров)
- [ ] Swagger полностью описывает API (параметры, примеры)
- [ ] Тесты на разные комбинации фильтров

**Критерии готовности (DoD):**
- ✅ API работает с любой комбинацией фильтров
- ✅ Время ответа < 200 мс (p95)
- ✅ Swagger актуален

**Приоритет:** P1 (high)
**Оценка:** 8 SP

---

#### Issue #87: Фасетный поиск

**Описание:**
Показывать **счётчики** для каждого фильтра: "Италия: 450 товаров", "Франция: 320".

**Зачем:**
Улучшение UX витрины: пользователь видит, сколько товаров в каждой категории.

**API:**
```
GET /api/v1/products/facets
  ?country=Италия  # если применён фильтр

Response:
{
  "countries": {
    "Италия": 450,
    "Франция": 320,
    "Испания": 180,
    "Германия": 95
  },
  "regions": {
    "Тоскана": 120,
    "Пьемонт": 85,
    "Венето": 70,
    "Бордо": 95
  },
  "colors": {
    "Красное": 380,
    "Белое": 250,
    "Розовое": 45,
    "Игристое": 110
  },
  "grapes": {
    "Санджовезе": 78,
    "Неббиоло": 45,
    "Пино Гриджио": 32,
    "Каберне Совиньон": 58
  },
  "styles": {
    "Сухое": 650,
    "Полусухое": 120,
    "Игристое": 110
  },
  "price_ranges": {
    "0-1000": 85,
    "1000-3000": 320,
    "3000-5000": 180,
    "5000+": 65
  }
}
```

**Реализация:**
```python
@app.route('/api/v1/products/facets', methods=['GET'])
def get_product_facets():
    """
    Получить фасеты (счётчики) для фильтров.
    Учитывает уже применённые фильтры.
    """

    # Собираем уже применённые фильтры
    applied_filters = {}
    for key in ['country', 'region', 'color', 'style', 'grape', 'producer']:
        value = request.args.get(key)
        if value:
            applied_filters[key] = value

    # Базовый WHERE из применённых фильтров
    base_where = []
    base_params = []

    for key, value in applied_filters.items():
        if key == 'grape':
            base_where.append("""
                exists(
                    select 1 from product_grape_blend pgb
                    join grapes g on g.id = pgb.grape_id
                    where pgb.product_id = p.id and g.name ilike %s
                )
            """)
        elif key == 'producer':
            base_where.append("pr.name ILIKE %s")
        else:
            base_where.append(f"p.{key} ILIKE %s")

        base_params.append(f"%{value}%")

    base_where_sql = ("WHERE " + " AND ".join(base_where)) if base_where else ""

    # Запросы для каждого фасета
    facets = {}

    # Страны
    facets['countries'] = dict(db.query_all(f"""
        select p.country, count(*) as cnt
        from products p
        left join producers pr on pr.id = p.producer_id
        {base_where_sql}
        group by p.country
        order by cnt desc
        limit 50
    """, base_params))

    # Регионы
    facets['regions'] = dict(db.query_all(f"""
        select p.region, count(*) as cnt
        from products p
        left join producers pr on pr.id = p.producer_id
        {base_where_sql}
        group by p.region
        order by cnt desc
        limit 50
    """, base_params))

    # Цвета
    facets['colors'] = dict(db.query_all(f"""
        select p.color, count(*) as cnt
        from products p
        left join producers pr on pr.id = p.producer_id
        {base_where_sql}
        group by p.color
        order by cnt desc
    """, base_params))

    # Сорта винограда (топ-50)
    facets['grapes'] = dict(db.query_all(f"""
        select g.name, count(distinct p.id) as cnt
        from products p
        left join producers pr on pr.id = p.producer_id
        join product_grape_blend pgb on pgb.product_id = p.id
        join grapes g on g.id = pgb.grape_id
        {base_where_sql}
        group by g.name
        order by cnt desc
        limit 50
    """, base_params))

    # Ценовые диапазоны
    facets['price_ranges'] = dict(db.query_all(f"""
        select
            case
                when p.price_final_rub < 1000 then '0-1000'
                when p.price_final_rub < 3000 then '1000-3000'
                when p.price_final_rub < 5000 then '3000-5000'
                else '5000+'
            end as range,
            count(*) as cnt
        from products p
        left join producers pr on pr.id = p.producer_id
        {base_where_sql}
        group by range
        order by range
    """, base_params))

    return jsonify(facets)
```

**Как это работает в UI (пример):**
```
Фильтры:
━━━━━━━━━━━━━━━━━━━━
Страна:
☐ Италия (450)
☐ Франция (320)
☐ Испания (180)
☐ Германия (95)

Цвет:
☑ Красное (380)  ← Применён
☐ Белое (250)
☐ Розовое (45)

Цена:
☐ до 1000 руб (85)
☐ 1000-3000 (320)
☑ 3000-5000 (180)  ← Применён
☐ от 5000 (65)
```

**Чеклист:**
- [ ] API `/products/facets` работает
- [ ] Индексы/матвью для скорости (< 100 мс)
- [ ] Фасеты учитывают применённые фильтры
- [ ] Кэширование в Redis (опционально, для нагруженных систем)
- [ ] Swagger документация
- [ ] Тест: фасеты обновляются при изменении фильтров

**Критерии готовности (DoD):**
- ✅ Фасеты отображаются корректно
- ✅ Время ответа < 100 мс
- ✅ UI может строить динамические фильтры

**Приоритет:** P2 (medium)
**Оценка:** 5 SP

---

#### Issue #88: JWT-авторизация (опционально)

**Описание:**
JWT-токены с ролями для разграничения доступа.

**Решение:**

```python
# api/auth.py
import jwt
from datetime import datetime, timedelta
from functools import wraps

SECRET_KEY = os.getenv("JWT_SECRET_KEY")

def create_token(user_id, role='viewer'):
    """Создать JWT-токен."""
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def verify_token(token):
    """Проверить JWT-токен."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def require_jwt(required_role='viewer'):
    """Декоратор для проверки JWT."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            token = request.headers.get('Authorization', '').replace('Bearer ', '')

            if not token:
                return jsonify({"error": "Missing token"}), 401

            payload = verify_token(token)
            if not payload:
                return jsonify({"error": "Invalid or expired token"}), 401

            # Проверка роли
            if payload['role'] != 'admin' and payload['role'] != required_role:
                return jsonify({"error": "Insufficient permissions"}), 403

            # Прокидываем user info в g
            g.user_id = payload['user_id']
            g.role = payload['role']

            return f(*args, **kwargs)
        return wrapped
    return decorator

# Использование
@app.route('/api/v1/admin/users', methods=['GET'])
@require_jwt(required_role='admin')
def get_users():
    """Только для администраторов."""
    ...
```

**Чеклист:**
- [ ] JWT-токены генерируются и проверяются
- [ ] Middleware проверяет токен и роль
- [ ] Rate limit дифференцирован (viewer: 100/hour, admin: 1000/hour)
- [ ] Swagger: Security Schemes (Bearer JWT)
- [ ] Тесты: 401/403

**Критерии готовности (DoD):**
- ✅ Публичные эндпоинты: без токена
- ✅ Защищённые: требуют JWT
- ✅ Разграничение ролей работает

**Приоритет:** P3 (low)
**Оценка:** 5 SP

---

## 🎯 Приоритеты (Must/Should/Could)

### Must-have (критично для бизнеса):
✅ Эти задачи обязательны — без них система не работает корректно.

- ✅ Issue #77: Идемпотентность (предотвращает дубли в истории)
- ✅ Issue #78: Даты из файла (правильная история цен)
- ✅ Issue #79: Планировщик (автоматизация импорта)
- ✅ Issue #84: DQ-гейты (качество данных, карантин)
- ✅ Issue #86: API каталога (для витрины/ботов)

### Should-have (важно, но не блокирует):
⚠️ Желательно сделать, улучшает UX и качество данных.

- ⚠️ Issue #80: Автоприём вложений (удобство)
- ⚠️ Issue #81: Мастер-данные (богатый каталог)
- ⚠️ Issue #85: Тест-покрытие ETL ≥ 60% (стабильность)
- ⚠️ Issue #89: Structured logging (отладка, audit)

### Could-have (улучшает, но можно отложить):
💡 Nice-to-have, делаем, если есть время.

- 💡 Issue #82: Кеги/розлив (HoReCa специфика)
- 💡 Issue #83: Остатки по локациям (детализация)
- 💡 Issue #87: Фасетный поиск (UX улучшение)
- 💡 Issue #88: JWT-авторизация
- 💡 Issue #90-91: Sentry + Prometheus (наблюдаемость)

---

## ⚠️ Риски и митигация

### **Риск 1: Формат прайса изменится**
**Вероятность:** Средняя
**Воздействие:** Высокое (парсер сломается)

**Митигация:**
- ✅ YAML-маппинг колонок (легко обновить без кода)
- ✅ Версионирование маппингов (dw_2025_v1.yaml, dw_2025_v2.yaml)
- ✅ Алерт при неизвестных колонках (< 80% распознано)
- ✅ Карантин файлов с низким качеством парсинга

**Пример версионирования:**
```yaml
# etl/mappings/dw_2025_v1.yaml
version: "1.0"
valid_from: "2025-01-01"
valid_until: "2025-06-30"
columns:
  Код: sku
  Наименование: product_name
  Цена прайс: price_list_rub
  # ...
```

---

### **Риск 2: PDF-каталог нечитаем (скан, плохое OCR)**
**Вероятность:** Низкая
**Воздействие:** Среднее (мастер-данные не загрузятся)

**Митигация:**
- ✅ Ручное извлечение первого раза + валидация (≥90% производителей)
- ✅ Требовать от поставщика машиночитаемые файлы (Word/Excel)
- ✅ Альтернатива: ручное заполнение справочников (100-200 производителей разово)

---

### **Риск 3: Отсутствие вложений в выходные**
**Вероятность:** Низкая
**Воздействие:** Низкое (данные устарели на 2 дня)

**Митигация:**
- ✅ Накопление файлов в понедельник (обработка за Fri-Mon)
- ✅ Идемпотентность предотвратит дубли
- ✅ Алерт при отсутствии файлов > 3 дней

---

### **Риск 4: Рост объёма данных (10K+ SKU, 1M+ строк истории)**
**Вероятность:** Средняя
**Воздействие:** Среднее (медленные запросы)

**Митигация:**
- ✅ Индексы на частые фильтры (country, region, price_range, abv)
- ✅ Партиционирование таблиц по датам (для истории цен/остатков)
- ✅ Кэширование фасетов в Redis (TTL 1 час)
- ✅ Мониторинг query performance (Prometheus slow_query_log)

---

## ✅ Критерии готовности (Definition of Done)

### Как понять, что Sprint 7-9 завершены?

**Технические критерии:**

1. **Идемпотентность:**
   - [ ] Повторная загрузка файла → лог "Already imported", 0 дублей в БД
   - [ ] Тест: загрузить файл 3 раза → 1 запись в `price_list`
   - [ ] Покрытие тестами ≥ 80%

2. **Даты:**
   - [ ] `product_prices.effective_from` = дата из шапки Excel
   - [ ] Тест: файл за 20 января → `price_date = 2025-01-20`
   - [ ] Fallback-цепочка работает (шапка → имя → mtime)

3. **Планировщик:**
   - [ ] Импорт срабатывает автоматически пн-пт в 08:10
   - [ ] Лог содержит timestamp, файлы, результаты
   - [ ] При ошибке → уведомление в Slack/email/Sentry
   - [ ] Архивирование успешных файлов работает

4. **Мастер-данные:**
   - [ ] Справочники заполнены из PDF (≥90% производителей)
   - [ ] При импорте Excel автоподтягиваются `producer_id`, `appellation_id`
   - [ ] API возвращает обогащённые карточки

5. **API:**
   - [ ] Swagger UI полностью актуален
   - [ ] Все эндпоинты работают (200 OK)
   - [ ] Тесты API: покрытие ≥ 80%
   - [ ] Время ответа p95 < 200 мс

**Бизнес-критерии:**

1. **Актуальность прайса:**
   - [ ] Задержка от получения файла до доступности в API ≤ 10 минут

2. **Качество данных:**
   - [ ] ≥ 95% строк проходят валидацию
   - [ ] Карантин работает (битые файлы не ломают систему)
   - [ ] DQ-отчёты автоматически генерируются

3. **Полнота каталога:**
   - [ ] 100% SKU имеют мастер-данные (производитель, регион, сорта)
   - [ ] Купажи корректно отображаются

4. **Стабильность:**
   - [ ] Uptime ≥ 99.5% за месяц
   - [ ] API latency p95 < 200 мс
   - [ ] 0 критических инцидентов за спринт

---

## 📚 Дополнительные материалы

### Документы для изучения:

1. **Бизнес-требования:**
   - `docs/business_requirements.md` — описание винного бизнеса, процессов
   - `docs/data_dictionary.md` — словарь данных (таблицы, поля, типы)

2. **Технические спецификации:**
   - `docs/database_schema.md` — схема БД с ER-диаграммой
   - `docs/etl_pipeline.md` — как работает импорт (блок-схема)
   - `docs/api_design.md` — принципы дизайна API, версионирование

3. **Операционные процедуры:**
   - `docs/deployment.md` — как деплоить (Docker/systemd)
   - `docs/monitoring.md` — что мониторить, алерты
   - `docs/troubleshooting.md` — типичные проблемы и решения

### Полезные ссылки:

- 📘 [PostgreSQL документация](https://www.postgresql.org/docs/16/)
- 📘 [Flask best practices](https://flask.palletsprojects.com/en/3.0.x/)
- 📘 [Cron syntax](https://crontab.guru/)
- 📘 [SHA256 в Python](https://docs.python.org/3/library/hashlib.html)
- 📘 [JWT.io](https://jwt.io/) — декодер JWT-токенов
- 📘 [OpenAPI 3.0 spec](https://swagger.io/specification/)

---

## 🗓️ Timeline (примерный график)

```
Ноябрь 2025 (Sprint 4-6 — текущие)
├─ Week 1-2: Sprint 4 (Tests)
│   └─ Цель: 60-80% coverage
├─ Week 3-4: Sprint 5 (Observability)
│   └─ Цель: structured logs, Prometheus, Sentry
└─ Week 5-6: Sprint 6 (User Features)
    └─ Цель: Telegram-бот, векторный поиск, экспорт

Декабрь 2025 (Sprint 7-9 — новые)
├─ Week 1-2: Sprint 7 (Idempotent Import)
│   ├─ #77: SHA256 + price_list таблица
│   ├─ #78: Даты из шапки Excel
│   ├─ #79: Cron-планировщик (пн-пт 08:10)
│   └─ #80: Email/inbox автоприём
│
├─ Week 3-4: Sprint 8 (Business Data)
│   ├─ #81: Мастер-данные из PDF
│   ├─ #82: Кеги + serving_prices
│   └─ #84: DQ-гейты (из Sprint 4-6)
│
└─ Week 5: Sprint 9 (API Extensions)
    ├─ #86: GET /products (расширенные фильтры)
    └─ #87: Фасетный поиск

Итого: ~2.5 месяца до полной готовности
       ~6 недель на Sprint 7-9
```

**Критические зависимости:**

- ⚠️ Sprint 7 НЕ НАЧИНАТЬ до завершения Sprint 4-6
- ⚠️ Issue #81 (мастер-данные) требует Issue #77-78 (идемпотентность + даты)
- ⚠️ Issue #87 (фасеты) требует Issue #86 (API) + Issue #81 (мастер-данные)
- ⚠️ Issue #84 (DQ) желательно после Issue #62 (structured logging)

---

## 📝 Контрольные вопросы (проверь себя)

Прочитал roadmap? Ответь на вопросы:

1. **Что такое идемпотентность?**
<details>
<summary>Подсказка</summary>
Операция идемпотентна, если её можно выполнить много раз, но результат будет как от одного выполнения.
Пример: кнопка "Сохранить" — нажал 10 раз, но сохранилось 1 раз.
</details>

2. **Зачем нужна таблица price_list?**
<details>
<summary>Подсказка</summary>
Журнал источников данных. Хранит SHA256 файла → проверка "Этот файл уже импортирован?"
</details>

3. **Откуда берётся дата прайса?**
<details>
<summary>Подсказка</summary>
Fallback-цепочка: 1) Шапка Excel → 2) Имя файла (regex) → 3) mtime файла
</details>

4. **Что делает cron 10 8 * * 1-5?**
<details>
<summary>Подсказка</summary>
Запускает задачу каждый день в 08:10, но только по будням (пн-пт).
</details>

5. **Зачем нужны мастер-данные (producers, regions)?**
<details>
<summary>Подсказка</summary>
Богатый каталог: фильтры по стране/региону/сорту, карточки товаров с описаниями, купажи.
</details>

6. **Что такое фасетный поиск?**
<details>
<summary>Подсказка</summary>
Показ счётчиков для фильтров: "Италия (450)", "Франция (320)" → пользователь видит, сколько товаров в каждой категории.
</details>

---

**Если не знаешь ответ → перечитай соответствующий раздел Issue!**

---

## 🎓 Следующие шаги (что делать с этим roadmap)

### **1. Сохранить в репозиторий:**
```bash
# Добавить файл в git
git add docs/roadmap_sprint7+.md

# Закоммитить с описательным сообщением
git commit -m "docs: add roadmap for Sprint 7-9 (business integration)

- Idempotent import (SHA256, price_list table)
- Extract price_date from Excel header
- Daily scheduler (cron Mon-Fri 08:10)
- Master data from PDF catalog (producers, regions, grapes)
- Kegs and servings support
- Extended API with filters and facets

Related to future sprints after completing #58-69"

# Запушить на GitHub
git push origin master
```

### **2. Обновлять roadmap по мере работы:**

**Когда завершишь Issue:**
```markdown
#### Issue #77: Идемпотентная загрузка прайсов ✅

**Статус:** Done (15 декабря 2025)
**Результат:** Идемпотентность работает, тесты проходят.
**PR:** #123
```

**Когда изменятся планы:**
```markdown
#### Issue #80: Автоприём вложений

**Статус:** Postponed → Sprint 10
**Причина:** Нашли готовую библиотеку `imap-tools`, проще чем писать с нуля.
```

### **3. Создавать issues по мере необходимости:**

Когда завершишь Sprint 4-6, создавай issues из roadmap:
```markdown
# GitHub Issue #77

**Title:** Идемпотентная загрузка прайсов

**Описание:**
Добавить механизм проверки "Этот файл уже загружен?" по SHA256-хэшу.
Детали в `docs/roadmap_sprint7+.md` (Issue #77).

**Чеклист:**
- [ ] Миграция `price_list` создана
- [ ] Функция `calculate_sha256()` реализована
- [ ] Проверка перед импортом работает
- [ ] Лог "Already imported"
- [ ] Тесты проходят

**DoD:**
- Повторная загрузка → 0 дублей
- Тест: файл 3 раза → 1 запись

**Labels:** enhancement, priority:critical, sprint:7
**Milestone:** Sprint 7 (Business Integration)
**Estimate:** 5 SP
```

### **4. Периодически пересматривать:**
- Раз в месяц перечитывай roadmap
- Обновляй оценки и сроки
- Добавляй новые идеи в раздел "Backlog"

---

## 📞 Вопросы и поддержка

**Есть вопросы по roadmap?**
- Создай discussion на GitHub: "Question: Sprint 7+ roadmap"
- Обсуди с командой (если есть)
- Обновляй этот документ по мере прояснения

**Хочешь добавить новую фичу?**
1. Опиши в GitHub Issue
2. Оцени сложность (Story Points)
3. Определи приоритет (Must/Should/Could)
4. Добавь в roadmap (раздел "Backlog")

**Нашёл ошибку в roadmap?**
- Создай PR с исправлением
- Укажи, что изменилось и почему

---

## 📌 Changelog roadmap

**v1.0 (31 октября 2025):**
- ✅ Первая версия roadmap
- ✅ Sprint 7-9 детально расписаны
- ✅ Приоритизация (Must/Should/Could)
- ✅ Риски и митигации
- ✅ Критерии готовности (DoD)

**v1.1 (планируется после Sprint 4-6):**
- 🔄 Уточнить оценки на основе реальной velocity
- 🔄 Добавить детали по интеграции с Telegram-ботом (#67)
- 🔄 Обновить схему БД с учётом мастер-данных

---

**🎉 Roadmap готов к использованию!**

Теперь у тебя есть чёткий план развития на ближайшие 2-3 месяца. Не спеши реализовывать всё сразу — **сначала закончи Sprint 4-6**, потом возвращайся к этому roadmap.

**Помни:**
- Roadmap — это **живой документ**. Обновляй его!
- Приоритеты могут меняться — это нормально.
- Лучше сделать **несколько задач хорошо**, чем все задачи плохо.

**Удачи в разработке! 🚀🍷**
