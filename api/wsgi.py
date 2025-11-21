"""
api/wsgi.py

WSGI entry point для production deployment с Gunicorn.

Использование:
    gunicorn --bind 0.0.0.0:8000 --workers 4 api.wsgi:app

Gunicorn параметры:
    --workers 4          - 4 worker процесса для параллельной обработки запросов
    --threads 2          - 2 потока на воркер (итого 8 одновременных запросов)
    --timeout 60         - таймаут 60 секунд на запрос
    --access-logfile -   - логи доступа в stdout
    --error-logfile -    - логи ошибок в stderr
    --log-level info     - уровень логирования

Пример команды:
    gunicorn --bind 0.0.0.0:8000 \\
             --workers 4 \\
             --threads 2 \\
             --timeout 60 \\
             --access-logfile - \\
             --error-logfile - \\
             --log-level info \\
             api.wsgi:app
"""

from api.app import app

# Gunicorn будет использовать этот объект app
if __name__ == "__main__":
    # Fallback для локального запуска (не рекомендуется для production)
    app.run()
