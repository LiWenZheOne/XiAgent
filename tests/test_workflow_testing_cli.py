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
    args = build_parser().parse_args(["--workflow-id", "deepseek_echo", "--input", '{"prompt":"hello"}'])

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
    workflow_file.write_text(
        """
workflow:
  id: cli-echo
  version: 1.0.0
  scope: global
  name: CLI Echo
  input_schema:
    type: object
    required: ["topic"]
    properties:
      topic:
        type: string
nodes:
  - id: echo
    ref: tool.echo.v1
    inputs:
      topic:
        from: "$workflow.input.topic"
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
    args = argparse.Namespace(
        workflow_path=workflow_file,
        workflow_id=None,
        input='{"topic":"cli"}',
        input_file=None,
        interactive=False,
        database_path=tmp_path / "workflow-test.sqlite3",
        asset_storage_dir=tmp_path / "assets",
        workflow_dir=workflow_dir,
        project_id=None,
        project_name="Workflow Test Project",
        username="workflow-test-admin",
        password="secret-123",
        show_json=False,
        open_images=False,
        preview=None,
        open_preview=False,
        debug=False,
    )

    exit_code = await run_from_args(args)

    assert exit_code == 0
