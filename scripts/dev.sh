#!/usr/bin/env bash
# Development mode (macOS/Linux): runs the FastAPI backend (:8000) and the Vite
# dev server (:5173, hot reload) together. Open http://localhost:5173
set -e
cd "$(dirname "$0")/.."

python -m uvicorn backend.main:app --reload --port 8000 &
API_PID=$!
trap "kill $API_PID 2>/dev/null" EXIT

cd frontend
npm install
npm run dev
