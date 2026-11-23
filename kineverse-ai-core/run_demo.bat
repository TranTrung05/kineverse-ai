@echo off
REM DEMO MODE: tay gia lap + Unity Mock chay cung tien trinh. Khong can camera/gang tay.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python backend\run_core.py --with-mock --demo
pause
