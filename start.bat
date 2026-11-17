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

:: 서버 종료 후 DB 자동 동기화
echo.
echo [동기화] 데이터 저장 중...
git add inventory.db >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
    for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set TODAY=%%a-%%b-%%c
    for /f "tokens=1-2 delims=: " %%a in ("%time%") do set NOW=%%a:%%b
    git commit -m "data: DB 자동 동기화 %TODAY% %NOW%" >nul 2>&1
    git push >nul 2>&1
    echo [완료] GitHub에 데이터 저장됨
) else (
    echo [확인] 변경된 데이터 없음
)
echo.
pause
