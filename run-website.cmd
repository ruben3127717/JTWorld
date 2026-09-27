@echo off
cd /d "%~dp0"
title JT World - Translation Studio
echo JT World - opening http://127.0.0.1:8765
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8765'"
if exist "%~dp0.venv312\Scripts\python.exe" (
  "%~dp0.venv312\Scripts\python.exe" "%~dp0web_app.py"
) else (
  "%~dp0..\.venv312\Scripts\python.exe" "%~dp0web_app.py"
)
pause
