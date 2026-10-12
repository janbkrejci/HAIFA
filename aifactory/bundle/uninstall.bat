@echo off
rem Uninstalls HAIFA on Windows: runs uninstall.ps1 next to this file. Double-click or run
rem from cmd; arguments (-Purge, -KeepData) go to uninstall.ps1.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
set "RC=%ERRORLEVEL%"
rem Started by double-click: keep the window open to read the result.
echo %CMDCMDLINE% | find /i "%~nx0" >nul && pause
exit /b %RC%
