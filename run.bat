@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe spectro_tool.py
) else (
    python spectro_tool.py
)
pause
