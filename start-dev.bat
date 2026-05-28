@echo off
setlocal

cd /d "%~dp0"

set "XIAGENT_ROOT=%CD%"
set "XIAGENT_API_SCRIPT=%XIAGENT_ROOT%\xiagent\api\start-api.bat"
set "XIAGENT_V2_SCRIPT=%XIAGENT_ROOT%\ui\V2\start-v2.bat"

if not defined XIAGENT_API_HOST set "XIAGENT_API_HOST=127.0.0.1"
if not defined XIAGENT_API_PORT set "XIAGENT_API_PORT=8000"
if not defined XIAGENT_V2_HOST set "XIAGENT_V2_HOST=127.0.0.1"
if not defined XIAGENT_V2_PORT set "XIAGENT_V2_PORT=5174"

if not exist "%XIAGENT_API_SCRIPT%" (
  echo API startup script was not found:
  echo %XIAGENT_API_SCRIPT%
  exit /b 1
)

if not exist "%XIAGENT_V2_SCRIPT%" (
  echo V2 frontend startup script was not found:
  echo %XIAGENT_V2_SCRIPT%
  exit /b 1
)

echo Starting XiAgent development services...
echo API: http://%XIAGENT_API_HOST%:%XIAGENT_API_PORT%
echo V2:  http://%XIAGENT_V2_HOST%:%XIAGENT_V2_PORT%
echo.
echo Two command windows will open. Close those windows to stop the services.
echo.

start "XiAgent API" cmd /k call "%XIAGENT_API_SCRIPT%"
timeout /t 2 /nobreak >nul
start "XiAgent V2" cmd /k call "%XIAGENT_V2_SCRIPT%"

endlocal
