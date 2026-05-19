from __future__ import annotations

import json
from pathlib import Path

from xiagent.workflows.testing.console import ConsoleIO, parse_input_data


def test_parse_input_data_prefers_inline_json(tmp_path: Path) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text('{"topic":"from-file"}', encoding="utf-8")

    parsed = parse_input_data(
        inline_json='{"topic":"from-inline"}',
        input_file=input_file,
        interactive=False,
        input_schema={"type": "object"},
        console=ConsoleIO(),
    )

    assert parsed == {"topic": "from-inline"}


def test_parse_input_data_reads_json_file(tmp_path: Path) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"topic": "from-file"}), encoding="utf-8")

    parsed = parse_input_data(
        inline_json=None,
        input_file=input_file,
        interactive=False,
        input_schema={"type": "object"},
        console=ConsoleIO(),
    )

    assert parsed == {"topic": "from-file"}


def test_parse_input_data_prompts_required_schema_fields() -> None:
    prompts: list[str] = []
    answers = iter(["hello", "7", "yes", '{"nested": true}'])
    console = ConsoleIO(input_func=lambda prompt: prompts.append(prompt) or next(answers))

    parsed = parse_input_data(
        inline_json=None,
        input_file=None,
        interactive=False,
        input_schema={
            "type": "object",
            "required": ["topic", "count", "enabled", "options"],
            "properties": {
                "topic": {"type": "string"},
                "count": {"type": "integer"},
                "enabled": {"type": "boolean"},
                "options": {"type": "object"},
            },
        },
        console=console,
    )

    assert parsed == {
        "topic": "hello",
        "count": 7,
        "enabled": True,
        "options": {"nested": True},
    }
    assert prompts == ["topic: ", "count: ", "enabled: ", "options (JSON): "]


from xiagent.workflows.testing import WorkflowTestBuilder
from xiagent.workflows.testing.runner import WorkflowTestRunner


def _echo_contract() -> dict:
    return {
        "workflow": {
            "id": "runner-echo",
            "version": "1.0.0",
            "scope": "global",
            "name": "Runner Echo",
            "input_schema": {
                "type": "object",
                "required": ["topic"],
                "properties": {"topic": {"type": "string"}},
            },
        },
        "nodes": [
            {
                "id": "echo",
                "ref": "tool.echo.v1",
                "inputs": {"topic": {"from": "$workflow.input.topic"}},
                "outputs": {"type": "object"},
            }
        ],
        "edges": [{"from": "START", "to": "echo"}, {"from": "echo", "to": "END"}],
    }


def _echo_image_contract() -> dict:
    contract = _echo_contract()
    contract["workflow"]["input_schema"] = {
        "type": "object",
        "required": ["topic", "image"],
        "properties": {
            "topic": {"type": "string"},
            "image": {"type": "string"},
        },
    }
    contract["nodes"][0]["inputs"] = {
        "topic": {"from": "$workflow.input.topic"},
        "image": {"from": "$workflow.input.image"},
    }
    return contract


def _approval_contract() -> dict:
    return {
        "workflow": {
            "id": "runner-approval",
            "version": "1.0.0",
            "scope": "global",
            "name": "Runner Approval",
            "input_schema": {
                "type": "object",
                "required": ["topic"],
                "properties": {"topic": {"type": "string"}},
            },
        },
        "nodes": [
            {
                "id": "review",
                "ref": "system.human_approval.v1",
                "inputs": {"topic": {"from": "$workflow.input.topic"}},
                "outputs": {
                    "type": "object",
                    "required": ["decision"],
                    "properties": {"decision": {"type": "string"}},
                },
            },
            {
                "id": "echo",
                "ref": "tool.echo.v1",
                "inputs": {"decision": {"from": "$nodes.review.output.decision"}},
                "outputs": {"type": "object"},
            },
        ],
        "edges": [
            {"from": "START", "to": "review"},
            {
                "from": "review",
                "to": "echo",
                "when": {"path": "$nodes.review.output.decision", "equals": "approve"},
            },
            {"from": "echo", "to": "END"},
        ],
    }


async def test_runner_executes_echo_contract_and_collects_events(tmp_path: Path) -> None:
    output_lines: list[str] = []
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(tmp_path / "workflows")
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(output_func=output_lines.append),
    )

    result = await runner.run_contract(_echo_contract(), input_data={"topic": "hello"})

    assert result.task.status == "succeeded"
    assert [event.event_type for event in result.events] == [
        "task_created",
        "task_started",
        "node_started",
        "node_succeeded",
        "task_succeeded",
    ]
    assert result.node_executions[0].output_snapshot == {"echo": {"topic": "hello"}}
    assert result.run_dir == tmp_path / "runs" / result.task.task_id
    assert "[01] 加载工作流 runner-echo 1.0.0" in output_lines


async def test_runner_prints_events_node_summary_and_image_paths(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    output_lines: list[str] = []
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(tmp_path / "workflows")
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(output_func=output_lines.append),
    )

    result = await runner.run_contract(
        _echo_image_contract(),
        input_data={"topic": "hello", "image": str(image_path)},
    )

    output = "\n".join(output_lines)
    assert result.task.status == "succeeded"
    assert "task_created" in output
    assert "node=echo" in output
    assert "[图片输出]" in output
    assert "path:" in output
    assert str(image_path) in output


async def test_runner_accepts_positional_session_and_console(tmp_path: Path) -> None:
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(tmp_path / "workflows")
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    runner = WorkflowTestRunner(session, ConsoleIO())

    result = await runner.run_contract(_echo_contract(), input_data={"topic": "hello"})

    assert result.task.status == "succeeded"


async def test_runner_returns_failed_task_for_missing_input_reference(tmp_path: Path) -> None:
    contract = _echo_contract()
    contract["workflow"]["input_schema"] = {
        "type": "object",
        "properties": {"missing": {"type": "string"}},
    }
    contract["nodes"][0]["inputs"] = {"topic": {"from": "$workflow.input.missing"}}
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(tmp_path / "workflows")
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    runner = WorkflowTestRunner(session=session, console=ConsoleIO())

    result = await runner.run_contract(contract, input_data={})

    assert result.task.status == "failed"
    assert result.events[-1].event_type == "task_failed"


async def test_runner_returns_failed_task_when_resume_continuation_fails(
    tmp_path: Path,
) -> None:
    contract = _approval_contract()
    contract["workflow"]["input_schema"] = {
        "type": "object",
        "properties": {"optional_field": {"type": "string"}},
    }
    contract["nodes"][0]["inputs"] = {}
    contract["nodes"][1]["inputs"] = {
        "value": {"from": "$workflow.input.optional_field"},
    }
    answers = iter(['{"decision":"approve"}'])
    console = ConsoleIO(input_func=lambda prompt: next(answers))
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(tmp_path / "workflows")
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    runner = WorkflowTestRunner(session=session, console=console)

    result = await runner.run_contract(contract, input_data={})

    assert result.task.status == "failed"
    assert result.events[-1].event_type == "task_failed"
    assert "task_resumed" in [event.event_type for event in result.events]


async def test_runner_preview_false_does_not_generate_preview(tmp_path: Path) -> None:
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(tmp_path / "workflows")
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    runner = WorkflowTestRunner(session=session, console=ConsoleIO())

    result = await runner.run_contract(
        _echo_contract(),
        input_data={"topic": "hello"},
        preview=False,
    )

    assert result.preview_path is None
    assert not (result.run_dir / "preview.html").exists()


async def test_runner_resumes_waiting_task_from_console(tmp_path: Path) -> None:
    answers = iter(['{"decision":"approve"}'])
    output_lines: list[str] = []
    console = ConsoleIO(
        input_func=lambda prompt: next(answers),
        output_func=output_lines.append,
    )
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(tmp_path / "workflows")
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    runner = WorkflowTestRunner(session=session, console=console)

    result = await runner.run_contract(_approval_contract(), input_data={"topic": "hello"})

    assert result.task.status == "succeeded"
    assert [item.node_id for item in result.node_executions] == ["review", "echo"]
    assert any("[等待输入] 节点 review" in line for line in output_lines)


async def test_runner_loads_contract_from_workflow_file(tmp_path: Path) -> None:
    workflow_file = tmp_path / "echo.workflow.yaml"
    workflow_file.write_text(
        """
workflow:
  id: file-echo
  version: 1.0.0
  scope: global
  name: File Echo
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
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(workflow_dir)
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    runner = WorkflowTestRunner(session=session, console=ConsoleIO())

    result = await runner.run_workflow_file(workflow_file, input_data={"topic": "file"})

    assert result.task.workflow_id == "file-echo"
    assert result.task.status == "succeeded"
