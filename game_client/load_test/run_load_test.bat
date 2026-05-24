@echo off
cd /d "%~dp0\.."
python -m pip install -r requirements.txt -q
python run_load_test.py %*
