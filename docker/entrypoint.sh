#!/bin/sh
set -e

python manage.py migrate --noinput
exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000
