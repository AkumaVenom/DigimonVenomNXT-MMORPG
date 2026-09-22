@echo off
setlocal
cd /d "%~dp0"
title Digimon Venom NXT - LOCAL DEVELOPMENT Server
if exist ".venv-dev\Scripts\python.exe" goto existing
py -3 -c "import sys,struct;sys.exit(0 if sys.version_info >= (3,11) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto python_launcher
python -c "import sys,struct;sys.exit(0 if sys.version_info >= (3,11) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto python_path
echo Install Python 3.11 or newer for Windows x64 and enable Add Python to PATH.
pause
exit /b 1
:existing
".venv-dev\Scripts\python.exe" tools\dev.py server %*
goto finished
:python_launcher
py -3 tools\dev.py server %*
goto finished
:python_path
python tools\dev.py server %*
:finished
set "RESULT=%ERRORLEVEL%"
echo.
echo Local development server stopped. This mode is only for this computer.
pause
exit /b %RESULT%
