@echo off
cd /d "%~dp0"
echo 기존 서버 종료 중...
taskkill /f /im python.exe >nul 2>&1
timeout /t 1 /nobreak >nul
echo 서버 시작 중...
start "" "http://localhost:8000"
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
