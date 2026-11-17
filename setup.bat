@echo off
chcp 65001 >nul
title 재고 관리 프로그램 설치

echo ============================================
echo   재고 관리 프로그램 설치
echo ============================================
echo.

:: Python 설치 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org 에서 Python 3.11 이상을 설치하세요.
    echo 설치 시 "Add Python to PATH" 를 반드시 체크하세요.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [확인] Python %PYVER% 발견

:: 가상환경 생성
if exist ".venv\Scripts\python.exe" (
    echo [확인] 가상환경이 이미 존재합니다. 건너뜁니다.
) else (
    echo [설치] 가상환경 생성 중...
    python -m venv .venv
    if errorlevel 1 (
        echo [오류] 가상환경 생성 실패
        pause
        exit /b 1
    )
    echo [완료] 가상환경 생성
)

:: 패키지 설치
echo [설치] 필요 패키지 설치 중...
.venv\Scripts\pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [오류] 패키지 설치 실패
    pause
    exit /b 1
)
echo [완료] 패키지 설치

echo.
echo ============================================
echo   설치 완료!
echo   start.bat 을 실행하면 서버가 시작됩니다.
echo ============================================
echo.
pause
