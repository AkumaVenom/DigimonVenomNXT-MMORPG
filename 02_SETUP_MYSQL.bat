@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title Digimon Venom NXT - Portable MySQL Setup
set "SETUP_COMMAND=wizard --stage database"
if not "%~1"=="" set "SETUP_COMMAND=mysql"
if /I "%~1"=="--wizard" set "SETUP_COMMAND=wizard --stage database"
call "%~dp0_RUN_SETUP.bat" %SETUP_COMMAND% %*
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" exit /b 0
echo.
echo Setup did not finish. Read the message above or logs\setup-latest.json.
pause
exit /b %RESULT%
