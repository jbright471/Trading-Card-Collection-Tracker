@echo off
cd /d "%~dp0"
if not exist "%~dp0data" mkdir "%~dp0data"
set "TCG_TRACKER_DATA_DIR=%~dp0data"
python app.py
pause
