@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Windows PowerShell is required.
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] adbgath installation failed with exit code %EXIT_CODE%.
  exit /b %EXIT_CODE%
)
echo.
echo Installation completed. Open a new terminal and run: adbgath doctor
exit /b 0
