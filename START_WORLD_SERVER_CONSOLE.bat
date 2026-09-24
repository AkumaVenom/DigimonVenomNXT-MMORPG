@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title Digimon Venom NXT - Dedicated World Server Console
call "%~dp0START_MYSQL.bat"
if errorlevel 1 exit /b 1
if exist "VenomWorldServer.exe" goto compiled
if exist ".venv-build\Scripts\python.exe" goto source
if exist ".venv-dev\Scripts\python.exe" goto dev_source
echo Build first with BUILD_ALL.bat. Run MySQL setup and hosting setup before starting.
pause
exit /b 1
:compiled
"VenomWorldServer.exe" --config config\server.json %*
goto finished
:source
".venv-build\Scripts\python.exe" -m venom.server.main --config config\server.json %*
goto finished
:dev_source
".venv-dev\Scripts\python.exe" -m venom.server.main --config config\server.json %*
goto finished
:finished
set "RESULT=%ERRORLEVEL%"
echo.
echo World server stopped. Review this console for errors.
echo MySQL stays running. Run STOP_SERVER.bat before copying or zipping this folder.
pause
exit /b %RESULT%
