@echo off
REM One-command production start (Windows): build the frontend, then serve the
REM whole app (API + UI) from FastAPI on http://localhost:8000
setlocal
cd /d "%~dp0\.."

echo [1/3] Installing Python dependencies...
pip install -r requirements.txt || goto :err

echo [2/3] Building the frontend...
pushd frontend
call npm install || goto :err
call npm run build || goto :err
popd

echo [3/3] Starting AnomalEye on http://localhost:8000 ...
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
goto :eof

:err
echo.
echo Build failed. See the messages above.
exit /b 1
