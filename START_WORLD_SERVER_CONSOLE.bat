@echo off
setlocal
cd /d "%~dp0"
title Digimon Venom NXT - Dedicated World Server Console
if exist "VenomWorldServer.exe" goto compiled
if exist ".venv-build\Scripts\python.exe" goto source
echo Build first with BUILD_ALL.bat. Run MySQL setup and hosting setup before starting.
pause
exit /b 1
:compiled
"VenomWorldServer.exe" --config config\server.json %*
goto finished
:source
".venv-build\Scripts\python.exe" -m venom.server.main --config config\server.json %*
:finished
set "RESULT=%ERRORLEVEL%"
echo.
echo World server stopped. Review this console for errors.
pause
exit /b %RESULT%
