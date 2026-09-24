@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
if exist "mysql\manager\VenomMySQL.exe" goto compiled
if exist ".venv-build\Scripts\python.exe" goto build_python
if exist ".venv-setup\Scripts\python.exe" goto setup_python
if exist ".venv-dev\Scripts\python.exe" goto dev_python
echo Run 01_SETUP_SERVER.bat or BUILD_ALL.bat first.
exit /b 1
:compiled
"mysql\manager\VenomMySQL.exe" --root "%CD%" %*
exit /b %ERRORLEVEL%
:build_python
".venv-build\Scripts\python.exe" -m tools.portable_mysql --root "%CD%" %*
exit /b %ERRORLEVEL%
:setup_python
".venv-setup\Scripts\python.exe" -m tools.portable_mysql --root "%CD%" %*
exit /b %ERRORLEVEL%
:dev_python
".venv-dev\Scripts\python.exe" -m tools.portable_mysql --root "%CD%" %*
exit /b %ERRORLEVEL%
