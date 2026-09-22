@echo off
setlocal
cd /d "%~dp0"
if exist "DigimonVenomNXT.exe" goto compiled
if exist ".venv-build\Scripts\python.exe" goto source
echo Run BUILD_ALL.bat or launch from the built Windows_Client_x64 folder.
pause
exit /b 1
:compiled
start "Digimon Venom NXT" "DigimonVenomNXT.exe" %*
exit /b 0
:source
".venv-build\Scripts\python.exe" -m venom.client.main %*
exit /b %ERRORLEVEL%
