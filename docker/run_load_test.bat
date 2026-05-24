@echo off
setlocal
cd /d "%~dp0.."
set PLAYERS=%1
if "%PLAYERS%"=="" set PLAYERS=200
docker compose --profile loadtest run --rm loadtest python run_load_test.py --players %PLAYERS% --accounts load_test/accounts.json --no-monitor --turbo %*
