@echo off
setlocal
cd /d "%~dp0"
echo Digimon Venom NXT - Microsoft Visual C++ runtime
powershell.exe -NoLogo -NoProfile -File "%~dp0install_vc_runtime.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
    echo You can now run START_MYSQL.bat from the server folder.
) else if "%RESULT%"=="3010" (
    echo Restart Windows before starting the server.
) else (
    echo Runtime setup did not finish. Read the message above.
)
pause
exit /b %RESULT%
