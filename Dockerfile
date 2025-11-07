# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# чтобы Python не писал .pyc и лог стримился сразу
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# curl нужен для healthcheck контейнера api (compose дергает /ready)
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# код приложения
COPY api/ ./api/
COPY scripts/ ./scripts/
COPY db/ ./db/
COPY .env.example .env

# безопасный пользователь
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# КЛЮЧЕВАЯ правка: запускать модульно, а не как файл
CMD ["python", "-m", "api.app"]
