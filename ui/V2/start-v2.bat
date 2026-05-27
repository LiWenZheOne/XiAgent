@echo off
setlocal

cd /d "%~dp0"

if not defined XIAGENT_V2_HOST set "XIAGENT_V2_HOST=127.0.0.1"
if not defined XIAGENT_V2_PORT set "XIAGENT_V2_PORT=5174"

where npm >nul 2>nul
if errorlevel 1 (
  echo npm was not found in PATH.
  exit /b 1
)

if not exist node_modules (
  echo Installing V2 frontend dependencies...
  call npm install
  if errorlevel 1 exit /b 1
)

echo Starting XiAgent V2 frontend...
echo URL: http://%XIAGENT_V2_HOST%:%XIAGENT_V2_PORT%
echo API proxy expects: http://127.0.0.1:8000
echo Start the API first: xiagent\api\start-api.bat
echo.

call npm run dev -- --host %XIAGENT_V2_HOST% --port %XIAGENT_V2_PORT%
