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
