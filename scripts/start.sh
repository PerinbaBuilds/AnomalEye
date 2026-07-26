#!/usr/bin/env bash
# One-command production start (macOS/Linux): build the frontend, then serve
# the whole app (API + UI) from FastAPI on http://localhost:8000
set -e
cd "$(dirname "$0")/.."

echo "[1/3] Installing Python dependencies..."
pip install -r requirements.txt

echo "[2/3] Building the frontend..."
(cd frontend && npm install && npm run build)

echo "[3/3] Starting AnomalEye on http://localhost:8000 ..."
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
