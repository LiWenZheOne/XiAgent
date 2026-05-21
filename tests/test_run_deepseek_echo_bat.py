from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _write_fake_python(tmp_path: Path, message: str = "fake python called") -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_python = bin_dir / "python.bat"
    fake_python.write_text(
        f"@echo off\r\necho {message} %*\r\nexit /b 0\r\n",
        encoding="utf-8",
    )
    return bin_dir


def _with_fake_python_on_path(bin_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir};{env.get('PATH', '')}"
    return env


@pytest.mark.skipif(sys.platform != "win32", reason="Windows batch behavior only")
def test_run_deepseek_echo_bat_without_args_keeps_interactive_menu(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "workflows" / "global" / "run_deepseek_echo_test.bat"
    bin_dir = _write_fake_python(tmp_path)

    result = subprocess.run(
        ["cmd", "/c", str(script)],
        cwd=project_root,
        env=_with_fake_python_on_path(bin_dir),
        input="workflows\\global\\deepseek_echo.workflow.yaml\r\n3\r\n",
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "Workflow path:" in result.stdout
    assert "Choose 1/2/3:" in result.stdout
    assert "ERROR:" not in result.stdout
    assert "fake python called" not in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows batch behavior only")
def test_run_deepseek_echo_bat_auto_mode_runs_without_menu(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "workflows" / "global" / "run_deepseek_echo_test.bat"
    bin_dir = _write_fake_python(tmp_path)

    result = subprocess.run(
        ["cmd", "/c", str(script), "--auto"],
        cwd=project_root,
        env=_with_fake_python_on_path(bin_dir),
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "fake python called -m xiagent.workflows.testing_cli" in result.stdout
    assert "Workflow path:" not in result.stdout
    assert "Press any key" not in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows batch behavior only")
def test_run_deepseek_echo_bat_returns_nonzero_for_missing_workflow() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "workflows" / "global" / "run_deepseek_echo_test.bat"

    result = subprocess.run(
        ["cmd", "/c", str(script), "workflows\\global\\missing.workflow.yaml", "1"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "Workflow file not found" in result.stdout
    assert "Press any key" not in result.stdout
