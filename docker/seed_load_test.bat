@echo off
setlocal
cd /d "%~dp0.."
set COUNT=%1
if "%COUNT%"=="" set COUNT=200

docker compose up -d web
if errorlevel 1 exit /b 1

docker compose exec web python manage.py seed_load_test_users --count %COUNT% --output game_client/load_test/accounts.json --force
