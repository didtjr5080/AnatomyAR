@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto setup
if not exist ".venv\setup-complete" goto setup
".venv\Scripts\python.exe" -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8" >nul 2>nul
if errorlevel 1 goto setup
goto launch
:setup
echo First launch: preparing Python and packages. Internet access is required.
call "%~dp0setup_windows.bat"
if errorlevel 1 exit /b 1
:launch
".venv\Scripts\python.exe" -m src.app %*
if not errorlevel 1 exit /b 0
if not "%CI%"=="true" pause
exit /b 1
