#!/usr/bin/env bash
# Digital Product Studio - one-click start for macOS / Linux
set -e
cd "$(dirname "$0")"
PY=python3
command -v $PY >/dev/null 2>&1 || { echo "Python 3.10+ is required: https://www.python.org/downloads/"; exit 1; }
if [ ! -d .venv ]; then
  echo "First run: setting up (this takes a few minutes)..."
  $PY -m venv .venv
  ./.venv/bin/pip install --upgrade pip -q
  ./.venv/bin/pip install -r requirements.txt -q
  ./.venv/bin/python -m playwright install chromium
fi
[ -f .env ] || cp .env.example .env
echo "Starting Digital Product Studio at http://127.0.0.1:8000"
( sleep 3; (command -v open >/dev/null && open http://127.0.0.1:8000) || (command -v xdg-open >/dev/null && xdg-open http://127.0.0.1:8000) ) >/dev/null 2>&1 &
cd backend && ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
