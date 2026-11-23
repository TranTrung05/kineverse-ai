@echo off
REM Cai moi truong: can Python 3.11 (64-bit) da cai, co "py launcher"
cd /d "%~dp0"
py -3.11 -m venv .venv || (echo Khong tim thay Python 3.11. Cai tu python.org roi chay lai. & pause & exit /b 1)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo Xong. Chay run_demo.bat (khong can camera) hoac run_camera.bat.
pause
