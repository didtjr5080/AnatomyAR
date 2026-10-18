@echo off
setlocal
cd /d "%~dp0"
set "PIP_CACHE_DIR=%CD%\.pip-cache"
set "PYTEST_DEBUG_TEMPROOT=%CD%\.test-tmp\%RANDOM%-%RANDOM%"
mkdir "%PYTEST_DEBUG_TEMPROOT%" >nul 2>nul
if /I "%~1"=="--offline" (
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "scripts\bootstrap_python.ps1" -Offline
) else (
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "scripts\bootstrap_python.ps1"
)
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m ensurepip --upgrade
if errorlevel 1 goto fail
if /I "%~1"=="--offline" (
  ".venv\Scripts\python.exe" -m pip install --no-index --find-links wheelhouse -r requirements.txt
) else (
  ".venv\Scripts\python.exe" -m pip install --only-binary=:all: -r requirements.txt
)
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -c "from src.tracking.mediapipe_tracker import verify_model,verify_gesture_model; verify_model(); verify_gesture_model()"
if errorlevel 1 goto modelmissing
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 goto fail
echo ready>".venv\setup-complete"
echo Setup verified. Run run_windows.bat
exit /b 0
:modelmissing
echo Model missing or damaged. When online, run:
echo .venv\Scripts\python.exe scripts\fetch_model.py
goto fail
:fail
echo Setup failed. Read docs\INSTALL.md. Existing files were not reset.
if not "%CI%"=="true" pause
exit /b 1
