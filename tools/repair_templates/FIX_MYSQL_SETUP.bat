@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title Digimon Venom NXT - Password Setup Repair
if not exist "setup_fix\repair_mysql.py" goto incomplete
if exist ".venv-build\Scripts\python.exe" goto checkbuild
:checkfix
if exist ".venv-setup-fix\Scripts\python.exe" goto checkfixpython
:checklauncher
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if not errorlevel 1 goto launcher
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if not errorlevel 1 goto python
echo Python 3.11 or newer is required for this one-time setup repair.
echo Install Windows Python with Tcl/Tk support and the Python launcher enabled.
echo Then run FIX_MYSQL_SETUP.bat again. You do not need to rebuild the game.
set "RESULT=1"
goto finished
:checkbuild
".venv-build\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto checkfix
".venv-build\Scripts\python.exe" "setup_fix\repair_mysql.py" --root "%CD%" %*
goto result
:checkfixpython
".venv-setup-fix\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto checklauncher
".venv-setup-fix\Scripts\python.exe" "setup_fix\repair_mysql.py" --root "%CD%" %*
goto result
:launcher
py -3 "setup_fix\repair_mysql.py" --root "%CD%" %*
goto result
:python
python "setup_fix\repair_mysql.py" --root "%CD%" %*
goto result
:incomplete
echo Setup repair files are missing.
echo Extract the entire repair ZIP next to VenomWorldServer.exe and try again.
set "RESULT=1"
goto finished
:result
set "RESULT=%ERRORLEVEL%"
:finished
echo.
pause
exit /b %RESULT%
