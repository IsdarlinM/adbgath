@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0portable.ps1" %*
exit /b %ERRORLEVEL%
