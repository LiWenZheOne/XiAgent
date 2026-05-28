from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from xiagent.api.app import create_app


def _echo_contract() -> dict[str, Any]:
    return {
        "workflow": {
            "id": "manual-observable-echo",
            "version": "1.0.0",
            "scope": "global",
            "name": "Manual Observable Echo",
            "input_schema": {
                "type": "object",
                "required": ["topic"],
                "properties": {"topic": {"type": "string"}},
            },
        },
        "nodes": [
            {
                "id": "collect_workflow_input",
                "ref": "system.workflow_input.v1",
                "inputs": {},
                "outputs": {
                    "type": "object",
                    "required": ["topic"],
                    "properties": {"topic": {"type": "string"}},
                },
            },
            {
                "id": "echo",
                "ref": "tool.echo.v1",
                "inputs": {"topic": {"from": "$workflow.input.topic"}},
                "outputs": {"type": "object"},
            }
        ],
        "edges": [
            {"from": "START", "to": "collect_workflow_input"},
            {"from": "collect_workflow_input", "to": "echo"},
            {"from": "echo", "to": "END"},
        ],
    }


def _log_step(step: int, title: str, payload: Any | None = None) -> None:
    print(f"\n[步骤 {step:02d}] {title}")
    if payload is not None:
        print(json.dumps(_redact_for_log(payload), ensure_ascii=False, indent=2, default=str))


def _redact_for_log(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***redacted***" if key == "access_token" else _redact_for_log(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_for_log(item) for item in value]
    return value


def _assert_ok(response, *, step: int, title: str) -> dict[str, Any]:
    _log_step(step, title, response.json())
    assert response.status_code == 200
    return response.json()


def test_logged_echo_workflow_process(test_settings) -> None:
    app = create_app(settings=test_settings)

    with TestClient(app) as client:
        health = _assert_ok(
            client.get("/api/health"),
            step=1,
            title="健康检查",
        )
        assert health == {"status": "ok"}

        user = _assert_ok(
            client.post(
                "/api/auth/register",
                json={"username": "workflow-log-user", "password": "secret-123"},
            ),
            step=2,
            title="注册测试用户",
        )

        login = _assert_ok(
            client.post(
                "/api/auth/login",
                json={"username": "workflow-log-user", "password": "secret-123"},
            ),
            step=3,
            title="登录并获取 bearer token",
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        assert login["user"]["user_id"] == user["user_id"]

        project = _assert_ok(
            client.post(
                "/api/projects",
                headers=headers,
                json={"name": "工作流日志测试项目"},
            ),
            step=4,
            title="创建项目",
        )
        project_id = project["project_id"]

        nodes = _assert_ok(
            client.get("/api/nodes", headers=headers),
            step=5,
            title="查看当前可用节点",
        )
        node_refs = {node["ref"] for node in nodes["items"]}
        assert "tool.echo.v1" in node_refs

        contract = _echo_contract()
        _log_step(6, "准备工作流契约", contract)

        task = _assert_ok(
            client.post(
                "/api/tasks",
                headers=headers,
                json={
                    "project_id": project_id,
                    "contract": contract,
                },
            ),
            step=7,
            title="创建并执行工作流任务",
        )
        assert task["status"] == "waiting"
        assert "collect_workflow_input" in task["current_view"]["active_node_outputs"]

        resumed = _assert_ok(
            client.post(
                f"/api/tasks/{task['task_id']}/interactions",
                headers=headers,
                json={
                    "project_id": project_id,
                    "node_id": "collect_workflow_input",
                    "output": {"topic": "观察一次完整工作流执行过程"},
                },
            ),
            step=8,
            title="提交起始输入节点",
        )
        assert resumed["status"] == "succeeded"

        detail = _assert_ok(
            client.get(
                f"/api/tasks/{task['task_id']}",
                headers=headers,
                params={"project_id": project_id},
            ),
            step=9,
            title="读取任务完整状态",
        )

    _log_step(10, "任务事件时间线", detail["events"])
    _log_step(11, "节点执行快照", detail["node_executions"])

    assert detail["task"]["status"] == "succeeded"
    assert [execution["node_id"] for execution in detail["node_executions"]] == [
        "collect_workflow_input",
        "echo",
    ]
    assert detail["node_executions"][1]["status"] == "succeeded"
    assert detail["node_executions"][1]["output_snapshot"] == {
        "echo": {"topic": "观察一次完整工作流执行过程"}
    }
    assert [event["event_type"] for event in detail["events"]] == [
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
