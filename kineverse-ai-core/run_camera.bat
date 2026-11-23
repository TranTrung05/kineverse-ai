@echo off
REM Camera that + Unity Mock. Neu khong mo duoc camera, tu roi ve DEMO MODE (co nhan ro tren dashboard).
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" backend\run_core.py --with-mock %*
) else (
  python backend\run_core.py --with-mock %*
)
pause
