# Лёгкая база
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Минимальные утилиты и зависимости, чтобы:
# - был curl (healthcheck)
# - собирались нативные пакеты (если в req есть psycopg2 без -binary)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        build-essential \
        libpq-dev \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*


# Ставим зависимости заранее для лучшего кэширования
COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    pip install -r requirements.txt

# Копируем исходники
COPY api/ ./api/
COPY scripts/ ./scripts/
COPY db/ ./db/
COPY etl/ ./etl/
# Если у вас есть .env.example и он нужен внутри контейнера как дефолт:
# COPY .env.example .env

# Непривилегированный пользователь
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# ВАЖНО: не используем -k gevent (его нет в зависимостях).
# Берём worker-class gthread, который не требует внешних библиотек.
# Кол-во воркеров/потоков можно управлять через env в compose.
CMD ["sh", "-lc", "gunicorn --bind 0.0.0.0:8000 \
  --workers ${GUNICORN_WORKERS:-2} \
  --threads ${GUNICORN_THREADS:-4} \
  --timeout ${GUNICORN_TIMEOUT:-60} \
  --worker-class gthread \
  api.wsgi:app"]
