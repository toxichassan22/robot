@echo off
REM === Robot Startup Script ===
REM Run from the brain/ directory

set "PROJECT_ROOT=%~dp0.."
set "PYTHONPATH=%PROJECT_ROOT%"

echo Starting Robot System...
echo Project Root: %PROJECT_ROOT%

REM Use portable Python
set "PYTHON=%PROJECT_ROOT%\config\tools\python310-embed\python.exe"

REM Start the Web Dashboard UI in a new window
echo Starting Dashboard UI...
start "Robot Dashboard" cmd /k "cd /d %PROJECT_ROOT%\dashboard && npm run dev"

set "TF_CPP_MIN_LOG_LEVEL=3"
set "GLOG_minloglevel=3"
set "GLOG_stderrthreshold=3"

REM Start the Brain
echo Starting Brain AI...
"%PYTHON%" -m brain.cli run

pause
