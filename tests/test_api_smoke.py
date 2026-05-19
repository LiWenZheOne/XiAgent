from __future__ import annotations

from fastapi.testclient import TestClient

from xiagent.api.app import create_app


def _echo_contract() -> dict:
    return {
        "workflow": {
            "id": "api-echo",
            "version": "1.0.0",
            "scope": "global",
            "name": "API Echo",
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


def test_health_endpoint_returns_ok(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_and_project_endpoints_create_and_list_projects(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        register_response = client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "secret-123"},
        )
        assert register_response.status_code == 200
        user = register_response.json()

        login_response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "secret-123"},
        )
        assert login_response.status_code == 200
        assert login_response.json()["user"]["user_id"] == user["user_id"]

        project_response = client.post(
            "/api/projects",
            json={
                "user_id": user["user_id"],
                "name": "Comic Project",
                "description": "API smoke test project",
            },
        )
        assert project_response.status_code == 200
        project = project_response.json()

        list_response = client.get("/api/projects", params={"user_id": user["user_id"]})
        assert list_response.status_code == 200
        assert [item["project_id"] for item in list_response.json()["items"]] == [
            project["project_id"]
        ]


def test_nodes_endpoint_lists_builtin_node_refs(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        response = client.get("/api/nodes")

    assert response.status_code == 200
    refs = {item["ref"] for item in response.json()["items"]}
    assert {"system.human_approval.v1", "tool.echo.v1", "ai.deepseek_chat.v1"} <= refs


def test_text_asset_create_and_search_endpoints(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        user = client.post(
            "/api/auth/register",
            json={"username": "asset-owner", "password": "secret-123"},
        ).json()
        project = client.post(
            "/api/projects",
            json={"user_id": user["user_id"], "name": "Asset Project"},
        ).json()

        create_response = client.post(
            "/api/assets/text",
            json={
                "user_id": user["user_id"],
                "scope": "project",
                "project_id": project["project_id"],
                "name": "Character Brief",
                "text": "A moonlit city courier named Lin.",
                "metadata": {"kind": "brief"},
            },
        )
        assert create_response.status_code == 200
        asset = create_response.json()

        search_response = client.get(
            "/api/assets/search",
            params={
                "user_id": user["user_id"],
                "scope": "project",
                "project_id": project["project_id"],
                "keyword": "courier",
            },
        )

    assert search_response.status_code == 200
    result = search_response.json()
    assert result["total"] == 1
    assert result["items"][0]["asset_id"] == asset["asset_id"]


def test_task_endpoints_create_succeeded_echo_task_and_read_it(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        user = client.post(
            "/api/auth/register",
            json={"username": "task-owner", "password": "secret-123"},
        ).json()
        project = client.post(
            "/api/projects",
            json={"user_id": user["user_id"], "name": "Task Project"},
        ).json()

        create_response = client.post(
            "/api/tasks",
            json={
                "user_id": user["user_id"],
                "project_id": project["project_id"],
                "contract": _echo_contract(),
                "input_data": {"topic": "API smoke"},
            },
        )
        assert create_response.status_code == 200
        task = create_response.json()
        assert task["status"] == "succeeded"

        read_response = client.get(
            f"/api/tasks/{task['task_id']}",
            params={"user_id": user["user_id"], "project_id": project["project_id"]},
        )

    assert read_response.status_code == 200
    body = read_response.json()
    assert body["task"]["task_id"] == task["task_id"]
    assert body["task"]["status"] == "succeeded"


def test_wrong_project_access_uses_standard_error_shape(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        owner = client.post(
            "/api/auth/register",
            json={"username": "owner", "password": "secret-123"},
        ).json()
        other = client.post(
            "/api/auth/register",
            json={"username": "other", "password": "secret-123"},
        ).json()
        owner_project = client.post(
            "/api/projects",
            json={"user_id": owner["user_id"], "name": "Owner Project"},
        ).json()
        other_project = client.post(
            "/api/projects",
            json={"user_id": other["user_id"], "name": "Other Project"},
        ).json()

        task = client.post(
            "/api/tasks",
            json={
                "user_id": owner["user_id"],
                "project_id": owner_project["project_id"],
                "contract": _echo_contract(),
                "input_data": {"topic": "private"},
            },
        ).json()

        response = client.get(
            f"/api/tasks/{task['task_id']}",
            params={"user_id": other["user_id"], "project_id": other_project["project_id"]},
        )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "project_access_denied",
            "message": "User does not have access to this project",
            "details": {"action": "task:read", "project_id": other_project["project_id"]},
        }
    }
