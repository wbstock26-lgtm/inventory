@echo off
chcp 65001 >nul
title 재고 관리 프로그램

:: 가상환경 확인
if not exist ".venv\Scripts\python.exe" (
    echo [오류] 설치가 되어 있지 않습니다.
    echo setup.bat 을 먼저 실행하세요.
    pause
    exit /b 1
)

:: 브라우저 열기 (서버 준비 후 3초 대기)
start "" /B cmd /C "timeout /t 3 >nul && start http://127.0.0.1:8000"

echo ============================================
echo   재고 관리 서버 시작
echo   http://127.0.0.1:8000
echo   종료하려면 이 창을 닫으세요.
echo ============================================
echo.

.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
