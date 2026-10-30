@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Chua cai dat. Hay chay setup.bat truoc.
    pause
    exit /b 1
)

REM run.bat          -> MOT cua so chua ca cong vao va cong ra (mac dinh)
REM run.bat in       -> chi cong vao
REM run.bat out      -> chi cong ra
if "%~1"=="" (
    ".venv\Scripts\python.exe" main.py
) else (
    ".venv\Scripts\python.exe" main.py --gate %~1
)

if errorlevel 1 (
    echo.
    echo Chuong trinh dung do loi. Xem thong bao phia tren.
    pause
)
