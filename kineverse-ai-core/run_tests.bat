@echo off
cd /d "%~dp0backend"
call ..\.venv\Scripts\activate.bat
python -m unittest discover -s tests -t . -v
pause
