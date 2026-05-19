from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from xiagent.api.app import create_app


def _auth_headers(
    client: TestClient,
    *,
    username: str,
    password: str = "secret-123",
) -> dict[str, str]:
    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200
    body = login_response.json()
    assert body["token_type"] == "bearer"
    return {"Authorization": f"Bearer {body['access_token']}"}


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
        login_body = login_response.json()
        assert login_body["user"]["user_id"] == user["user_id"]
        assert login_body["token_type"] == "bearer"
        headers = {"Authorization": f"Bearer {login_body['access_token']}"}

        project_response = client.post(
            "/api/projects",
            json={
                "name": "Comic Project",
                "description": "API smoke test project",
            },
            headers=headers,
        )
        assert project_response.status_code == 200
        project = project_response.json()
        assert project["owner_user_id"] == user["user_id"]

        list_response = client.get("/api/projects", headers=headers)
        assert list_response.status_code == 200
        assert [item["project_id"] for item in list_response.json()["items"]] == [
            project["project_id"]
        ]


def test_protected_api_requires_valid_bearer_token(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        response = client.get("/api/projects")
        invalid_response = client.get(
            "/api/projects",
            headers={"Authorization": "Bearer invalid-token"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_access_token"
    assert invalid_response.status_code == 401
    assert invalid_response.json()["error"]["code"] == "invalid_access_token"


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
        headers = _auth_headers(client, username="asset-owner")
        project = client.post(
            "/api/projects",
            json={"name": "Asset Project"},
            headers=headers,
        ).json()

        create_response = client.post(
            "/api/assets/text",
            json={
                "scope": "project",
                "project_id": project["project_id"],
                "name": "Character Brief",
                "text": "A moonlit city courier named Lin.",
                "metadata": {"kind": "brief"},
            },
            headers=headers,
        )
        assert create_response.status_code == 200
        asset = create_response.json()
        assert asset["created_by"] == user["user_id"]

        search_response = client.get(
            "/api/assets/search",
            params={
                "scope": "project",
                "project_id": project["project_id"],
                "keyword": "courier",
            },
            headers=headers,
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
        headers = _auth_headers(client, username="task-owner")
        project = client.post(
            "/api/projects",
            json={"name": "Task Project"},
            headers=headers,
        ).json()

        create_response = client.post(
            "/api/tasks",
            json={
                "project_id": project["project_id"],
                "contract": _echo_contract(),
                "input_data": {"topic": "API smoke"},
            },
            headers=headers,
        )
        assert create_response.status_code == 200
        task = create_response.json()
        assert task["status"] == "succeeded"
        assert task["user_id"] == user["user_id"]

        read_response = client.get(
            f"/api/tasks/{task['task_id']}",
            params={"project_id": project["project_id"]},
            headers=headers,
        )

    assert read_response.status_code == 200
    body = read_response.json()
    assert body["task"]["task_id"] == task["task_id"]
    assert body["task"]["status"] == "succeeded"


def test_protected_post_routes_reject_body_user_id(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "body-user", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="body-user")
        project_response = client.post(
            "/api/projects",
            json={"user_id": "malicious-user", "name": "Bad Project"},
            headers=headers,
        )
        project = client.post(
            "/api/projects",
            json={"name": "Real Project"},
            headers=headers,
        ).json()
        asset_response = client.post(
            "/api/assets/text",
            json={
                "user_id": "malicious-user",
                "scope": "project",
                "project_id": project["project_id"],
                "name": "Bad Asset",
                "text": "blocked",
            },
            headers=headers,
        )
        task_response = client.post(
            "/api/tasks",
            json={
                "user_id": "malicious-user",
                "project_id": project["project_id"],
                "contract": _echo_contract(),
                "input_data": {"topic": "blocked"},
            },
            headers=headers,
        )

    assert project_response.status_code == 422
    assert project_response.json()["error"]["code"] == "request_validation_failed"
    assert asset_response.status_code == 422
    assert asset_response.json()["error"]["code"] == "request_validation_failed"
    assert task_response.status_code == 422
    assert task_response.json()["error"]["code"] == "request_validation_failed"


def test_protected_get_routes_reject_query_user_id(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "query-user", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="query-user")
        project = client.post(
            "/api/projects",
            json={"name": "Query Project"},
            headers=headers,
        ).json()
        task = client.post(
            "/api/tasks",
            json={
                "project_id": project["project_id"],
                "contract": _echo_contract(),
                "input_data": {"topic": "query"},
            },
            headers=headers,
        ).json()

        projects_response = client.get(
            "/api/projects",
            params={"user_id": "malicious-user"},
            headers=headers,
        )
        assets_response = client.get(
            "/api/assets/search",
            params={
                "user_id": "malicious-user",
                "scope": "project",
                "project_id": project["project_id"],
            },
            headers=headers,
        )
        task_response = client.get(
            f"/api/tasks/{task['task_id']}",
            params={"user_id": "malicious-user", "project_id": project["project_id"]},
            headers=headers,
        )

    for response in [projects_response, assets_response, task_response]:
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "unsupported_user_id_parameter"


def test_wrong_project_access_uses_standard_error_shape(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "owner", "password": "secret-123"},
        )
        owner_headers = _auth_headers(client, username="owner")
        client.post(
            "/api/auth/register",
            json={"username": "other", "password": "secret-123"},
        )
        other_headers = _auth_headers(client, username="other")
        owner_project = client.post(
            "/api/projects",
            json={"name": "Owner Project"},
            headers=owner_headers,
        ).json()
        other_project = client.post(
            "/api/projects",
            json={"name": "Other Project"},
            headers=other_headers,
        ).json()

        task = client.post(
            "/api/tasks",
            json={
                "project_id": owner_project["project_id"],
                "contract": _echo_contract(),
                "input_data": {"topic": "private"},
            },
            headers=owner_headers,
        ).json()

        response = client.get(
            f"/api/tasks/{task['task_id']}",
            params={"project_id": other_project["project_id"]},
            headers=other_headers,
        )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "project_access_denied",
            "message": "User does not have access to this project",
            "details": {"action": "task:read", "project_id": other_project["project_id"]},
        }
    }


def test_workflows_endpoint_loads_nested_workflow_files(test_settings) -> None:
    workflow_dir = test_settings.workflow_dir
    nested_dir = workflow_dir / "global"
    nested_dir.mkdir(parents=True)
    (nested_dir / "sample.workflow.yaml").write_text(
        """
workflow:
  id: nested-sample
  version: 1.0.0
  scope: global
  name: Nested Sample
  input_schema:
    type: object
    required:
      - topic
    properties:
      topic:
        type: string
nodes:
  - id: echo
    ref: tool.echo.v1
    inputs:
      topic:
        from: $workflow.input.topic
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
    app = create_app(settings=replace(test_settings, workflow_dir=workflow_dir))

    with TestClient(app) as client:
        response = client.get("/api/workflows")

    assert response.status_code == 200
    workflow_ids = {item["workflow"]["id"] for item in response.json()["items"]}
    assert "nested-sample" in workflow_ids


def test_request_validation_errors_use_standard_error_shape(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        response = client.post("/api/auth/register", json={"username": "missing-password"})

    assert response.status_code == 422
    body = response.json()
    assert "detail" not in body
    assert body["error"]["code"] == "request_validation_failed"
    assert body["error"]["message"]
    assert body["error"]["details"]
