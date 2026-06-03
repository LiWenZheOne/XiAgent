@echo off
setlocal

cd /d "%~dp0..\.."

if not defined XIAGENT_API_HOST set "XIAGENT_API_HOST=127.0.0.1"
if not defined XIAGENT_API_PORT set "XIAGENT_API_PORT=8008"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found in PATH.
  exit /b 1
)

echo Starting XiAgent API...
echo URL: http://%XIAGENT_API_HOST%:%XIAGENT_API_PORT%
echo Health: http://%XIAGENT_API_HOST%:%XIAGENT_API_PORT%/api/health
echo.

python -m uvicorn xiagent.api.app:app --reload --host %XIAGENT_API_HOST% --port %XIAGENT_API_PORT%
