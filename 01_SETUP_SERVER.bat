@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title Digimon Venom NXT - Portable Server Setup
set "SETUP_COMMAND=wizard"
call "%~dp0_RUN_SETUP.bat" %SETUP_COMMAND% %*
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" exit /b 0
echo.
echo Setup did not finish. Read the message above or logs\setup-latest.json.
pause
exit /b %RESULT%
