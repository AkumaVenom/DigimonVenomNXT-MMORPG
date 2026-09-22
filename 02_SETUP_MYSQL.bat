@echo off
setlocal
cd /d "%~dp0"
title Digimon Venom NXT - 02 MySQL Setup
if exist "admin\VenomSetup.exe" goto compiled
if exist ".venv-build\Scripts\python.exe" goto source
echo Run BUILD_ALL.bat first, or use this file inside Windows_Server_x64.
pause
exit /b 1
:compiled
"admin\VenomSetup.exe" --root "%CD%" mysql %*
goto finished
:source
".venv-build\Scripts\python.exe" -m tools.setup --root "%CD%" mysql %*
:finished
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
