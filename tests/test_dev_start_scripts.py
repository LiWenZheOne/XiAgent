from __future__ import annotations

from pathlib import Path


def test_api_start_script_runs_uvicorn_from_project_root() -> None:
    script = Path("xiagent/api/start-api.bat")

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert 'cd /d "%~dp0..\\.."' in content
    assert "python -m uvicorn xiagent.api.app:app" in content
    assert "--host %XIAGENT_API_HOST%" in content
    assert "--port %XIAGENT_API_PORT%" in content


def test_v2_start_script_runs_vite_dev_server() -> None:
    script = Path("ui/V2/start-v2.bat")

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert 'cd /d "%~dp0"' in content
    assert "call npm install" in content
    assert "call npm run dev -- --host %XIAGENT_V2_HOST% --port %XIAGENT_V2_PORT%" in content


def test_stop_dev_script_kills_default_api_and_v2_ports() -> None:
    script = Path("stop-dev.bat")

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert 'set "XIAGENT_API_PORT=8000"' in content
    assert 'set "XIAGENT_V2_PORT=5174"' in content
    assert "Get-NetTCPConnection -LocalPort $port -State Listen" in content
    assert "Get-CimInstance Win32_Process" in content
    assert "vite.js" in content
    assert "start-api.bat" in content
    assert "start-v2.bat" in content
    assert "& taskkill /PID $id /T /F" in content
