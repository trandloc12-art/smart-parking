@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Cai dat Smart Parking (chay MOT LAN) ===

where python >nul 2>nul
if errorlevel 1 (
    echo [LOI] Khong tim thay Python. Cai Python 3.10+ tu python.org va tick "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Dang tao moi truong ao .venv ...
    python -m venv .venv
    if errorlevel 1 goto :loi
)

echo Dang cai thu vien (lan dau co the mat vai phut) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :loi

if not exist ".env"     copy ".env.example"     ".env"     >nul && echo Da tao .env     - hay mo ra sua DB_SERVER, DB_USER...
if not exist ".env.in"  copy ".env.in.example"  ".env.in"  >nul && echo Da tao .env.in  - sua RFID_PORT, CAMERA_INDEX cua cong VAO
if not exist ".env.out" copy ".env.out.example" ".env.out" >nul && echo Da tao .env.out - sua RFID_PORT, CAMERA_INDEX cua cong RA

echo.
echo === Xong. Sua cac file .env* neu can, roi bam dup run.bat de chay. ===
pause
exit /b 0

:loi
echo.
echo [LOI] Cai dat that bai. Xem thong bao phia tren.
pause
exit /b 1
