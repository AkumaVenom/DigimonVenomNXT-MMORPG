@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title Digimon Venom NXT - Portable MySQL
call "%~dp0_RUN_MYSQL.bat" stop-server %*
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
