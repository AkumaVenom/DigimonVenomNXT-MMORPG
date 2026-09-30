@echo off
setlocal
cd /d "%~dp0"
title Digimon Venom NXT - v1.2.0 Retained Fixed Sprite Verification
if not exist "venom\version.py" goto wrong_folder
if not exist "data\fixed_sprites_v110.json" goto wrong_folder
if not exist "data\fixed_sprites_v111.json" goto wrong_folder
if not exist "tools\fixed_sprites_v111.py" goto wrong_folder
set "PYTHON_EXE="
for %%P in (".venv-dev\Scripts\python.exe" ".venv-build\Scripts\python.exe" ".venv\Scripts\python.exe") do if not defined PYTHON_EXE if exist %%P set "PYTHON_EXE=%%~P"
if defined PYTHON_EXE goto use_environment
py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 goto use_launcher
python -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 goto use_path
echo ERROR: Python 3.11 or newer is required. Use the existing source build environment.
echo This verifier does not install packages or change server data.
pause
exit /b 1
:use_environment
"%PYTHON_EXE%" tools\fixed_sprites_v111.py --verify
goto finished
:use_launcher
py -3 tools\fixed_sprites_v111.py --verify
goto finished
:use_path
python tools\fixed_sprites_v111.py --verify
goto finished
:wrong_folder
echo ERROR: Extract the complete v1.2.0 source archive before verifying.
echo This file belongs beside BUILD_ALL.bat, assets, data, tools and venom.
pause
exit /b 1
:finished
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" echo SUCCESS: Fixed sprites, catalog references and asset hashes verified.
if not "%RESULT%"=="0" echo FAILED: Read the error above. Do not assume the patch is complete.
pause
exit /b %RESULT%
