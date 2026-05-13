@echo off
setlocal enabledelayedexpansion
title Robot Auto-Setup ^& Launcher
color 0A

echo ===================================================
echo        ROBOT AUTO-SETUP ^& LAUNCHER
echo ===================================================
echo.

:: 1. Check Python Virtual Environment
if not exist "venv\Scripts\activate.bat" (
    echo [1/3] Python Virtual Environment not found. Creating 'venv'...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create Python virtual environment. Make sure Python is installed.
        pause
        exit /b 1
    )
    echo Virtual Environment created successfully!
) else (
    echo [1/3] Python Virtual Environment is ready.
)

:: Activate the virtual environment
call venv\Scripts\activate.bat

:: 2. Check and Install Python Dependencies
echo.
echo [2/3] Checking Python dependencies (requirements.txt)...
if exist "requirements.txt" (
    :: Run pip install. It will be very fast if everything is already installed.
    pip install -r requirements.txt --quiet
    echo Python dependencies are up to date!
) else (
    echo No requirements.txt found in the root directory. Skipping.
)

:: 3. Check and Install Node.js Dependencies (Dashboard)
echo.
echo [3/3] Checking Node.js Dashboard dependencies...
if exist "dashboard\package.json" (
    cd dashboard
    if not exist "node_modules\" (
        echo Dashboard 'node_modules' not found. Installing via npm...
        call npm install
    ) else (
        echo Dashboard dependencies are ready.
    )
    cd ..
) else (
    echo No dashboard folder found. Skipping Node.js setup.
)

echo.
echo ===================================================
echo     ALL SYSTEMS READY! LAUNCHING ROBOT...
echo ===================================================
echo.

:: Start Dashboard
echo Starting Dashboard UI...
start "Robot Dashboard" cmd /k "cd /d %~dp0dashboard && npm run dev"

:: Start Brain Backend using the activated venv
echo Starting Brain AI...
set "PYTHONPATH=%~dp0"
set "TF_CPP_MIN_LOG_LEVEL=3"
set "GLOG_minloglevel=3"
set "GLOG_stderrthreshold=3"

python -m brain.cli run
pause
