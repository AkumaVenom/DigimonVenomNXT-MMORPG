@echo off
setlocal DisableDelayedExpansion
call "%~dp0START_WORLD_SERVER_CONSOLE.bat" %*
exit /b %ERRORLEVEL%
