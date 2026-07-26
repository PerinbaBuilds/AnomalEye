@echo off
REM Development mode (Windows): starts the FastAPI backend (:8000) in a new
REM window and the Vite dev server (:5173, with hot reload) in this one.
REM Open http://localhost:5173
setlocal
cd /d "%~dp0\.."

start "AnomalEye API" cmd /k python -m uvicorn backend.main:app --reload --port 8000

cd frontend
call npm install
call npm run dev
