@echo off
setlocal
cd /d "%~dp0"
title Digimon Venom NXT - v1.3.0 Super Xros Wars Verification
set "PYTHON_EXE="
for %%P in (".venv-dev\Scripts\python.exe" ".venv-build\Scripts\python.exe" ".venv\Scripts\python.exe") do if not defined PYTHON_EXE if exist %%P set "PYTHON_EXE=%%~P"
if not defined PYTHON_EXE (
  echo Run BUILD_ALL.bat first to prepare the source environment.
  pause
  exit /b 1
)
"%PYTHON_EXE%" tools\build.py --verify-only
if errorlevel 1 goto failed
"%PYTHON_EXE%" -c "import pytest" >nul 2>&1
if errorlevel 1 (
  echo Install the test dependencies once, then run this verifier again:
  echo "%PYTHON_EXE%" -m pip install -r requirements-dev.txt
  pause
  exit /b 1
)
"%PYTHON_EXE%" -m pytest -q tests -k xros
if errorlevel 1 goto failed
echo SUCCESS: Super Xros Wars assets and gameplay checks passed.
pause
exit /b 0
:failed
echo FAILED: Read the error above. No saved server data has been changed.
pause
exit /b 1
