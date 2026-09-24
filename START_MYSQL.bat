@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title Digimon Venom NXT - Portable MySQL
call "%~dp0_RUN_MYSQL.bat" start %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo MySQL is not ready. Run 02_SETUP_MYSQL.bat for first-time setup.
exit /b %RESULT%
