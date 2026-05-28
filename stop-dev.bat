@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "XIAGENT_ROOT=%CD%"
if not defined XIAGENT_API_PORT set "XIAGENT_API_PORT=8000"
if not defined XIAGENT_V2_PORT set "XIAGENT_V2_PORT=5174"

echo Stopping XiAgent development services...
echo API port: %XIAGENT_API_PORT%
echo V2 port:  %XIAGENT_V2_PORT%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'SilentlyContinue';" ^
  "$ports = @($env:XIAGENT_API_PORT, $env:XIAGENT_V2_PORT) | ForEach-Object { if ($_ -match '^\d+$') { [int]$_ } };" ^
  "$pids = [System.Collections.Generic.HashSet[int]]::new();" ^
  "foreach ($port in $ports) {" ^
  "  Get-NetTCPConnection -LocalPort $port -State Listen | ForEach-Object { [void]$pids.Add([int]$_.OwningProcess) };" ^
  "}" ^
  "$root = (Resolve-Path $env:XIAGENT_ROOT).Path;" ^
  "$patterns = @('xiagent.api.app:app', 'uvicorn', 'npm run dev', 'node_modules\vite', 'vite.js', 'start-api.bat', 'start-v2.bat');" ^
  "Get-CimInstance Win32_Process | Where-Object { $cmd = $_.CommandLine; $_.ProcessId -ne $PID -and $cmd -and $cmd.IndexOf($root, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and ($patterns | Where-Object { $cmd -like ('*' + $_ + '*') }) } | ForEach-Object { [void]$pids.Add([int]$_.ProcessId) };" ^
  "if ($pids.Count -eq 0) { Write-Host 'No XiAgent development processes found.'; exit 0 };" ^
  "foreach ($id in $pids) {" ^
  "  Write-Host ('Stopping process {0}...' -f $id);" ^
  "  & taskkill /PID $id /T /F;" ^
  "}"

echo.
echo Done.
exit /b 0
