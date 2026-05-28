from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from xiagent.workflows.testing import WorkflowTestBuilder
from xiagent.workflows.testing.console import ConsoleIO, parse_input_data
from xiagent.workflows.testing.runner import WorkflowTestRunner


def test_console_prompts_resume_single_string_output_with_question() -> None:
    prompts: list[str] = []
    output_lines: list[str] = []
    console = ConsoleIO(
        input_func=lambda prompt: prompts.append(prompt) or "蓝色",
        output_func=output_lines.append,
    )

    output = console.prompt_resume_output(
        {
            "node_id": "ask_color",
            "status": "waiting",
            "metadata": {"requested_inputs": {"question": "请告诉我你喜欢的颜色。"}},
        },
        {
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string", "minLength": 1}},
            "additionalProperties": False,
        },
    )

    assert output == {"answer": "蓝色"}
    assert prompts == ["请告诉我你喜欢的颜色。\nanswer: "]
    assert "resume output JSON: " not in prompts


def test_console_replaces_unencodable_output_for_gbk_console() -> None:
    output_lines: list[str] = []

    def gbk_output(message: str) -> None:
        output_lines.append(message.encode("gbk").decode("gbk"))

    console = ConsoleIO(output_func=gbk_output)

    console.show_node_execution(
        {
            "node_id": "profile",
            "status": "succeeded",
            "output": {"text": "warning: ⚠"},
        }
    )

    assert any("warning: ?" in line for line in output_lines)


def test_default_console_output_survives_gbk_pythonioencoding() -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "gbk"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from xiagent.workflows.testing.console import ConsoleIO; "
                "ConsoleIO().show_node_execution("
                "{'node_id':'profile','status':'succeeded',"
                "'output':{'text':'warning: \\u26a0'}})"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="gbk",
        timeout=10,
    )

    assert result.returncode == 0
    assert "warning: ?" in result.stdout
    assert "UnicodeEncodeError" not in result.stderr


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


def test_parse_input_data_interactive_inline_json_prompts_missing_required_fields() -> None:
    prompts: list[str] = []
    answers = iter(["9:16", "1k"])
    console = ConsoleIO(input_func=lambda prompt: prompts.append(prompt) or next(answers))

    parsed = parse_input_data(
        inline_json='{"prompt":"from-inline"}',
        input_file=None,
        interactive=True,
        input_schema={
            "type": "object",
            "required": ["prompt", "aspect_ratio", "resolution"],
            "properties": {
                "prompt": {"type": "string", "minLength": 1},
                "aspect_ratio": {"type": "string", "minLength": 1},
                "resolution": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        console=console,
    )

    assert parsed == {
        "prompt": "from-inline",
        "aspect_ratio": "9:16",
        "resolution": "1k",
    }
    assert prompts == ["aspect_ratio: ", "resolution: "]


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


def test_parse_input_data_reads_bom_json_file(tmp_path: Path) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"topic": "from-file"}), encoding="utf-8-sig")

    parsed = parse_input_data(
        inline_json=None,
        input_file=input_file,
        interactive=False,
        input_schema={"type": "object"},
        console=ConsoleIO(),
    )

    assert parsed == {"topic": "from-file"}


def test_parse_input_data_uses_empty_object_for_schema_without_required_fields() -> None:
    def fail_on_prompt(prompt: str) -> str:
        raise AssertionError(f"unexpected prompt: {prompt}")

    parsed = parse_input_data(
        inline_json=None,
        input_file=None,
        interactive=True,
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
        console=ConsoleIO(input_func=fail_on_prompt),
    )

    assert parsed == {}


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


def _echo_contract() -> dict:
    return _with_user_input_node({
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
                "inputs": {"topic": {"from": "$nodes.collect_user_input.output.topic"}},
                "outputs": {"type": "object"},
            }
        ],
        "edges": [{"from": "START", "to": "echo"}, {"from": "echo", "to": "END"}],
    })


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
    next(node for node in contract["nodes"] if node["id"] == "collect_user_input")[
        "outputs"
    ] = contract["workflow"]["input_schema"]
    next(node for node in contract["nodes"] if node["id"] == "collect_user_input")[
        "inputs"
    ] = _user_input_specs(contract["workflow"]["input_schema"])
    contract["nodes"][0]["inputs"] = {
        "topic": {"from": "$nodes.collect_user_input.output.topic"},
        "image": {"from": "$nodes.collect_user_input.output.image"},
    }
    return contract


def _approval_contract() -> dict:
    return _with_user_input_node({
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
                "inputs": {"topic": {"from": "$nodes.collect_user_input.output.topic"}},
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
    })


def _first_node_user_input_contract() -> dict:
    return {
        "workflow": {
            "id": "first-node-input",
            "version": "1.0.0",
            "scope": "global",
            "name": "First Node Input",
            "input_schema": {"type": "object", "additionalProperties": False},
        },
        "nodes": [
            {
                "id": "ask_color",
                "ref": "system.human_approval.v1",
                "inputs": {
                    "question": {"value": "请告诉我你喜欢的颜色。"},
                    "answer": {
                        "from_user": True,
                        "schema": {"type": "string", "minLength": 1},
                    },
                },
                "outputs": {
                    "type": "object",
                    "required": ["answer"],
                    "properties": {"answer": {"type": "string", "minLength": 1}},
                    "additionalProperties": False,
                },
            },
            {
                "id": "echo",
                "ref": "tool.echo.v1",
                "inputs": {"answer": {"from": "$nodes.ask_color.output.answer"}},
                "outputs": {"type": "object"},
            },
        ],
        "edges": [
            {"from": "START", "to": "ask_color"},
            {"from": "ask_color", "to": "echo"},
            {"from": "echo", "to": "END"},
        ],
    }


def _with_user_input_node(contract: dict) -> dict:
    input_schema = contract["workflow"].get("input_schema", {})
    if not input_schema.get("properties"):
        return contract
    contract["nodes"].append(
        {
            "id": "collect_user_input",
            "ref": "system.user_input.v1",
            "inputs": _user_input_specs(input_schema),
            "outputs": input_schema,
        }
    )
    contract["edges"] = [
        {"from": "START", "to": "collect_user_input"},
        *[
            (
                {"from": "collect_user_input", "to": edge["to"]}
                if edge["from"] == "START"
                else edge
            )
            for edge in contract["edges"]
        ],
    ]
    return contract


def _user_input_specs(input_schema: dict) -> dict[str, dict]:
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    if not isinstance(properties, dict):
        return {}
    return {
        name: {
            "from_user": True,
            "schema": dict(schema) if isinstance(schema, dict) else {},
            "required": name in required,
        }
        for name, schema in properties.items()
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
        "node_waiting",
        "human_input_requested",
        "task_waiting",
        "task_resumed",
        "node_succeeded",
        "node_started",
        "node_succeeded",
        "task_succeeded",
    ]
    assert [item.node_id for item in result.node_executions] == [
        "collect_user_input",
        "echo",
    ]
    assert result.node_executions[0].output_snapshot == {"topic": "hello"}
    assert result.node_executions[1].output_snapshot == {"echo": {"topic": "hello"}}
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
    next(node for node in contract["nodes"] if node["id"] == "collect_user_input")[
        "outputs"
    ] = contract["workflow"]["input_schema"]
    next(node for node in contract["nodes"] if node["id"] == "collect_user_input")[
        "inputs"
    ] = _user_input_specs(contract["workflow"]["input_schema"])
    contract["nodes"][0]["inputs"] = {"topic": {"from": "$nodes.collect_user_input.output.missing"}}
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
    next(node for node in contract["nodes"] if node["id"] == "collect_user_input")[
        "outputs"
    ] = contract["workflow"]["input_schema"]
    next(node for node in contract["nodes"] if node["id"] == "collect_user_input")[
        "inputs"
    ] = _user_input_specs(contract["workflow"]["input_schema"])
    contract["nodes"][0]["inputs"] = {}
    contract["nodes"][1]["inputs"] = {
        "value": {"from": "$nodes.collect_user_input.output.optional_field"},
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


async def test_runner_preview_generates_html_and_prints_path(tmp_path: Path) -> None:
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
        _echo_contract(),
        input_data={"topic": "hello"},
        preview=True,
    )

    assert result.preview_path == result.run_dir / "preview.html"
    assert result.preview_path.exists()
    assert any(
        line.startswith("preview:") and "preview.html" in line
        for line in output_lines
    )


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
    assert [item.node_id for item in result.node_executions] == [
        "collect_user_input",
        "review",
        "echo",
    ]
    assert any("[等待输入] 节点 review" in line for line in output_lines)


async def test_runner_prompts_first_node_input_when_initial_payload_is_empty(
    tmp_path: Path,
) -> None:
    prompts: list[str] = []
    console = ConsoleIO(
        input_func=lambda prompt: prompts.append(prompt) or "蓝色",
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

    result = await runner.run_contract(_first_node_user_input_contract(), input_data={})

    assert result.task.status == "succeeded"
    assert result.node_executions[0].input_snapshot == {
        "question": "请告诉我你喜欢的颜色。",
        "answer": "蓝色",
    }
    assert result.node_executions[0].output_snapshot == {"answer": "蓝色"}
    assert prompts == ["answer: "]


async def test_runner_loads_contract_from_workflow_file(tmp_path: Path) -> None:
    workflow_file = tmp_path / "echo.workflow.yaml"
    workflow_file.write_text(
        """
workflow:
  id: file-echo
  version: 1.0.0
  scope: global
  name: File Echo
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
