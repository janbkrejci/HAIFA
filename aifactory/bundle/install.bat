@echo off
rem Installs HAIFA on Windows: runs install.ps1 next to this file. Double-click or run from cmd.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set "RC=%ERRORLEVEL%"
rem Started by double-click: keep the window open to read the result.
echo %CMDCMDLINE% | find /i "%~nx0" >nul && pause
exit /b %RC%
