@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
if exist "admin\VenomSetup.exe" goto compiled
if exist ".venv-build\Scripts\python.exe" goto build
if exist ".venv-dev\Scripts\python.exe" goto dev
if exist ".venv-setup\Scripts\python.exe" goto setup
py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 goto launcher
python -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 goto system
echo Install Python 3.11 or newer for Windows x64, or use the built server package.
exit /b 1
:compiled
"admin\VenomSetup.exe" --root "%CD%" %*
exit /b %ERRORLEVEL%
:build
".venv-build\Scripts\python.exe" -m tools.setup --root "%CD%" %*
exit /b %ERRORLEVEL%
:dev
".venv-dev\Scripts\python.exe" -m tools.setup --root "%CD%" %*
exit /b %ERRORLEVEL%
:setup
".venv-setup\Scripts\python.exe" tools\repair_mysql.py --root "%CD%" --command %*
exit /b %ERRORLEVEL%
:launcher
py -3 tools\repair_mysql.py --root "%CD%" --command %*
exit /b %ERRORLEVEL%
:system
python tools\repair_mysql.py --root "%CD%" --command %*
exit /b %ERRORLEVEL%
