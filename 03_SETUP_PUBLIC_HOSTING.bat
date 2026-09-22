@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title Digimon Venom NXT - Hosting Setup
set "SETUP_COMMAND=wizard --stage hosting"
if "%~1"=="" goto launch
if /I "%~1"=="--wizard" goto launch
set "SETUP_COMMAND=hosting"
:launch
if exist "admin\VenomSetup.exe" goto compiled
if exist ".venv-build\Scripts\python.exe" goto source
echo Run BUILD_ALL.bat first, or use this file inside Windows_Server_x64.
pause
exit /b 1
:compiled
"admin\VenomSetup.exe" --root "%CD%" %SETUP_COMMAND% %*
goto finished
:source
".venv-build\Scripts\python.exe" -m tools.setup --root "%CD%" %SETUP_COMMAND% %*
:finished
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" exit /b 0
echo.
echo Setup did not finish. Read the message above or logs\setup-latest.json.
pause
exit /b %RESULT%
