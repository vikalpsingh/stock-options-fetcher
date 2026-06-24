@echo off
setlocal
cd /d "%~dp0"

set PORT=3000

echo Installing dependencies...
call npm.cmd install
if errorlevel 1 goto :error

echo Building application...
call npm.cmd run build
if errorlevel 1 goto :error

echo Stopping server on port %PORT%...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    taskkill /PID %%P /F >nul 2>&1
)

echo Starting production server on port %PORT%...
start "Ujjain Travel Guide" /B cmd /c "npm.cmd run start -- -p %PORT%"

echo.
echo Server restarted: http://localhost:%PORT%/
exit /b 0

:error
echo.
echo Build or installation failed.
exit /b 1