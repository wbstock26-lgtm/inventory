@echo off
cd /d "%~dp0"
echo ============================================
echo  Little Red Deer Store 재고 관리 시스템
echo  http://localhost:8000
echo ============================================
echo.
echo 서버 시작 중... 잠시 후 브라우저가 열립니다.
start "" /B timeout /t 2 /nobreak >nul
start "" "http://localhost:8000"
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
pause
