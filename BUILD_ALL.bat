@echo off
setlocal
cd /d "%~dp0"
title Digimon Venom NXT - Windows x64 One Click Builder
echo Digimon Venom NXT - native Windows x64 client and dedicated server
echo This downloads dependencies into an isolated .venv-build folder.
echo Your supplied assets are verified before anything is built.
echo.
py -3 -c "import sys,struct;sys.exit(0 if sys.version_info >= (3,11) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto python_launcher
python -c "import sys,struct;sys.exit(0 if sys.version_info >= (3,11) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto python_path
echo ERROR: Install Python 3.11 or newer for Windows x64 first.
echo Select Add Python to PATH in the installer, then run this file again.
echo Official installer: https://www.python.org/downloads/windows/
pause
exit /b 1
:python_launcher
py -3 tools\build.py %*
goto finished
:python_path
python tools\build.py %*
:finished
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo Build failed. Read the error above; no success is assumed.
if "%RESULT%"=="0" echo Complete. Open dist for the separate Windows client and server packages.
pause
exit /b %RESULT%
