@echo off
cd /d "%~dp0"
echo Spectro Inspector — dependency installer
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

echo Creating virtual environment (.venv)...
python -m venv .venv
if errorlevel 1 (
    echo WARNING: Could not create virtual environment; installing into system Python.
    pip install -r requirements.txt
) else (
    echo Activating virtual environment and installing dependencies...
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
    echo.
    echo Done. Run the tool with:  run.bat
)
echo.
pause
