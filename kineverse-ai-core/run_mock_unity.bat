@echo off
REM Chay Unity Mock rieng (khi muon chay AI Core khong kem --with-mock). Co the them --fail-rate 0.2 --drop-rate 0.1
cd /d "%~dp0backend"
call ..\.venv\Scripts\activate.bat
python -m kineverse.mock_unity --port 8766
pause
