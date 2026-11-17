@echo off
cd /d "%~dp0"
echo ============================================
echo  Little Red Deer Store 재고 관리 시스템
echo  패키지 설치
echo ============================================
echo.
pip install -r requirements.txt
echo.
echo 설치 완료! start.bat 을 실행하세요.
echo.
pause
