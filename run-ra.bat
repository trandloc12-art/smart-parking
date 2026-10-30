@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Chua cai dat. Hay chay setup.bat truoc.
    pause
    exit /b 1
)

REM Chi chay cong RA (mot cua so).
".venv\Scripts\python.exe" main.py --gate out
if errorlevel 1 (
    echo.
    echo Chuong trinh dung do loi. Xem thong bao phia tren.
    pause
)
