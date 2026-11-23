@echo off
REM (Tuy chon, CHUA kiem thu) Dong goi bang PyInstaller.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
pip install pyinstaller
pyinstaller --noconfirm --onedir --name KineverseAICore --paths backend --add-data "dashboard;dashboard" --add-data "config.json;." --collect-all mediapipe backend\run_core.py
echo Ket qua: dist\KineverseAICore\KineverseAICore.exe
pause
