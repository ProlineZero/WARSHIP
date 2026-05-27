#!/bin/sh
set -e

# Миграции — напрямую в Postgres (PgBouncer transaction mode их ломает).
MIGRATE_HOST="${MIGRATE_DB_HOST:-${DB_HOST:-db}}"
MIGRATE_PORT="${MIGRATE_DB_PORT:-${DB_PORT:-5432}}"

echo "Ожидание PostgreSQL (${MIGRATE_HOST}:${MIGRATE_PORT})..."
attempt=0
max_attempts=30
until DB_HOST="$MIGRATE_HOST" DB_PORT="$MIGRATE_PORT" python -c "
import os, sys
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db import connection
connection.ensure_connection()
"; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "PostgreSQL недоступен после ${max_attempts} попыток" >&2
        exit 1
    fi
    sleep 2
done

echo "Применение миграций..."
DB_HOST="$MIGRATE_HOST" DB_PORT="$MIGRATE_PORT" python manage.py migrate --noinput

echo "Запуск uvicorn..."
exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000
