@echo off
setlocal
cd /d "%~dp0"
title Digimon Venom NXT - LOCAL DEVELOPMENT Client
if exist ".venv-dev\Scripts\python.exe" goto ready
echo Run START_LOCAL_DEV.bat first and wait for the local server to start.
pause
exit /b 1
:ready
".venv-dev\Scripts\python.exe" tools\dev.py client %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" pause
exit /b %RESULT%
