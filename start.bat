@echo off
REM Digital Product Studio - one-click start for Windows
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
if not exist .venv (
  echo First run: setting up - this takes a few minutes...
  python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip -q
  .venv\Scripts\pip install -r requirements.txt -q
  .venv\Scripts\python -m playwright install chromium
)
if not exist .env copy .env.example .env
echo Starting Digital Product Studio at http://127.0.0.1:8000
start "" http://127.0.0.1:8000
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
