@echo off
REM Gang tay that qua Serial. Sua COM3 cho dung cong (Device Manager).
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python backend\run_core.py --with-mock --glove-mode serial --glove-port COM3
pause
