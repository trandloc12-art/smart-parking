@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Chua cai dat. Hay chay setup.bat truoc.
    pause
    exit /b 1
)

REM Mo 2 cua so rieng: CONG VAO va CONG RA (moi cong mot tien trinh).
REM Dong cua so cua cong nao thi chi cong do dung. Cua so dong lenh hien thong bao loi neu co.
start "CONG VAO" cmd /k .venv\Scripts\python.exe main.py --gate in
timeout /t 2 /nobreak >nul
start "CONG RA" cmd /k .venv\Scripts\python.exe main.py --gate out
