from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from xiagent.workflows.testing_cli import build_parser, run_from_args


def test_build_parser_accepts_workflow_path_and_input() -> None:
    args = build_parser().parse_args(
        ["workflows/global/deepseek_echo.workflow.yaml", "--input", '{"prompt":"hello"}']
    )

    assert args.workflow_path == Path("workflows/global/deepseek_echo.workflow.yaml")
    assert args.input == '{"prompt":"hello"}'
    assert args.workflow_id is None


def test_build_parser_accepts_workflow_id() -> None:
    args = build_parser().parse_args(
        ["--workflow-id", "deepseek_echo", "--input", '{"prompt":"hello"}']
    )

    assert args.workflow_path is None
    assert args.workflow_id == "deepseek_echo"


def test_parser_rejects_missing_workflow_selector() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--input", '{"prompt":"hello"}'])


def test_parser_rejects_both_workflow_selectors() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["workflow.yaml", "--workflow-id", "deepseek_echo", "--input", '{"prompt":"hello"}']
        )


async def test_run_from_args_executes_workflow_file(tmp_path: Path) -> None:
    workflow_file = tmp_path / "echo.workflow.yaml"
    _write_echo_workflow(workflow_file, workflow_id="cli-echo")
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    args = _make_args(
        tmp_path,
        workflow_path=workflow_file,
        workflow_id=None,
        input_json='{"topic":"cli"}',
        workflow_dir=workflow_dir,
    )

    exit_code = await run_from_args(args)

    assert exit_code == 0


async def test_run_from_args_validates_workflow_file_before_prompting(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_file = tmp_path / "invalid.workflow.yaml"
    workflow_file.write_text(
        """
workflow:
  id: invalid-cli
  version: 1.0.0
  scope: global
nodes:
  - id: echo
    ref: tool.echo.v1
    inputs: {}
    outputs:
      type: object
edges:
  - from: START
    to: echo
  - from: echo
    to: END
""".lstrip(),
        encoding="utf-8",
    )
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    args = _make_args(
        tmp_path,
        workflow_path=workflow_file,
        workflow_id=None,
        input_json=None,
        workflow_dir=workflow_dir,
    )

    exit_code = await run_from_args(args)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "invalid_workflow_contract" in output
    assert "KeyError" not in output


async def test_run_from_args_executes_workflow_id(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_echo_workflow(workflow_dir / "cli.workflow.yaml", workflow_id="cli-id")
    args = _make_args(
        tmp_path,
        workflow_path=None,
        workflow_id="cli-id",
        input_json='{"topic":"cli"}',
        workflow_dir=workflow_dir,
    )

    exit_code = await run_from_args(args)

    assert exit_code == 0


async def test_run_from_args_prints_json_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_file = tmp_path / "echo.workflow.yaml"
    _write_echo_workflow(workflow_file, workflow_id="cli-json")
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    args = _make_args(
        tmp_path,
        workflow_path=workflow_file,
        workflow_id=None,
        input_json='{"topic":"cli"}',
        workflow_dir=workflow_dir,
        show_json=True,
    )

    exit_code = await run_from_args(args)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"task"' in output
    assert '"events"' in output
    assert '"node_executions"' in output


def _write_echo_workflow(path: Path, *, workflow_id: str) -> None:
    path.write_text(
        f"""
workflow:
  id: {workflow_id}
  version: 1.0.0
  scope: global
  name: CLI Echo
nodes:
  - id: collect_user_input
    ref: system.user_input.v1
    inputs:
      topic:
        from_user: true
        schema:
          type: string
        required: true
    outputs:
      type: object
      required: ["topic"]
      properties:
        topic:
          type: string
  - id: echo
    ref: tool.echo.v1
    inputs:
      topic:
        from: "$nodes.collect_user_input.output.topic"
    outputs:
      type: object
edges:
  - from: START
    to: collect_user_input
  - from: collect_user_input
    to: echo
  - from: echo
    to: END
""".lstrip(),
        encoding="utf-8",
    )


def _make_args(
    tmp_path: Path,
    *,
    workflow_path: Path | None,
    workflow_id: str | None,
    input_json: str | None,
    workflow_dir: Path,
    show_json: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        workflow_path=workflow_path,
        workflow_id=workflow_id,
        input=input_json,
        input_file=None,
        interactive=False,
        database_path=tmp_path / "workflow-test.sqlite3",
        asset_storage_dir=tmp_path / "assets",
        workflow_dir=workflow_dir,
        project_id=None,
        project_name="Workflow Test Project",
        username="workflow-test-admin",
        password="secret-123",
        show_json=show_json,
        open_images=False,
        preview=None,
        open_preview=False,
        debug=False,
    )
