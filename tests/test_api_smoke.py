from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from xiagent.api.app import create_app
from xiagent.api.routers.tasks import _task_episode_name, _task_uses_episode_summary
from xiagent.infrastructure.database import connect_db
from xiagent.infrastructure.migrations import migrate
from xiagent.models import ChatModelRouter, ChatRequest, ChatResponse
from xiagent.runtime.models import NodeExecutionRecord


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


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


def test_task_episode_name_prefers_latest_node_snapshot() -> None:
    assert _task_uses_episode_summary("asset_catalog")
    assert _task_uses_episode_summary("asset_storyboard_generation")
    assert not _task_uses_episode_summary("storyboard_generation")
    executions = [
        NodeExecutionRecord(
            node_execution_id="node-old",
            task_id="task-1",
            node_id="collect_asset_catalog_input",
            node_ref="system.user_input.v1",
            attempt=1,
            input_snapshot={},
            output_snapshot={"episode_name": "22、上一集"},
            status="succeeded",
            error=None,
            metadata={},
            started_at=None,
            finished_at=None,
            created_at="2026-05-31T00:00:00Z",
            updated_at="2026-05-31T00:00:00Z",
        ),
        NodeExecutionRecord(
            node_execution_id="node-new",
            task_id="task-1",
            node_id="finish_summary",
            node_ref="tool.episode_metadata_finalize.v1",
            attempt=1,
            input_snapshot={"episode_name": "23、私放晁天王"},
            output_snapshot={},
            status="succeeded",
            error=None,
            metadata={},
            started_at=None,
            finished_at=None,
            created_at="2026-05-31T00:01:00Z",
            updated_at="2026-05-31T00:01:00Z",
        ),
    ]

    assert _task_episode_name(executions) == "23、私放晁天王"


def _echo_contract() -> dict:
    return _with_user_input_node({
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
                "inputs": {"topic": {"from": "$nodes.collect_user_input.output.topic"}},
                "outputs": {"type": "object"},
            }
        ],
        "edges": [{"from": "START", "to": "echo"}, {"from": "echo", "to": "END"}],
    })


def _approval_contract() -> dict:
    return _with_user_input_node({
        "workflow": {
            "id": "api-approval",
            "version": "1.0.0",
            "scope": "global",
            "name": "API Approval",
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


def _storyboard_prompt_interaction_contract() -> dict:
    object_item_schema = {"type": "object", "additionalProperties": True}
    results_schema = {
        "type": "object",
        "required": ["results"],
        "properties": {"results": {"type": "array", "items": object_item_schema}},
        "additionalProperties": False,
    }
    waiting_outputs = {
        "type": "object",
        "required": ["decision", "panel_results"],
        "properties": {
            "decision": {"type": "string"},
            "panel_results": {"type": "array", "items": object_item_schema},
        },
        "additionalProperties": True,
    }
    return {
        "workflow": {
            "id": "api-storyboard-prompt-interaction",
            "version": "1.0.0",
            "scope": "global",
            "name": "API Storyboard Prompt Interaction",
        },
        "nodes": [
            {
                "id": "review_storyboard_image",
                "ref": "system.human_approval.v1",
                "inputs": {
                    "decision": {
                        "from_user": True,
                        "schema": {"type": "string"},
                    },
                    "panel_results": {
                        "from_user": True,
                        "schema": {"type": "array", "items": object_item_schema},
                    },
                },
                "outputs": waiting_outputs,
            },
            {
                "id": "analyze_scene_layout",
                "ref": "ai.parallel_deepseek_structured_json.v1",
                "inputs": _parallel_storyboard_node_inputs(
                    "请分析当前段落的实际场景布局 {paragraph_text}",
                    passthrough_fields=[
                        "index",
                        "paragraph_text",
                        "panel_count",
                        "present_characters",
                        "location",
                        "key_props",
                        "segment_assignment",
                    ],
                ),
                "outputs": results_schema,
            },
            {
                "id": "plan_storyboard_panels",
                "ref": "ai.parallel_deepseek_structured_json.v1",
                "inputs": {
                    **_parallel_storyboard_node_inputs(
                        "请为当前段落规划一页漫画分镜 {paragraph_text}",
                        passthrough_fields=[
                            "index",
                            "paragraph_text",
                            "panel_count",
                            "present_characters",
                            "location",
                            "key_props",
                            "segment_assignment",
                            "scene_layout",
                        ],
                    ),
                    "items": {"from": "$nodes.analyze_scene_layout.output.results"},
                },
                "outputs": results_schema,
            },
            {
                "id": "review_and_refine_storyboard_plan",
                "ref": "ai.storyboard_review_refine.v1",
                "inputs": _review_storyboard_node_inputs(
                    items_from="$nodes.plan_storyboard_panels.output.results",
                    review_prompt="请用提问方式审查当前段落的结构化分镜计划 {source}",
                    revision_prompt="请根据审查意见修订结构化分镜计划 {source}",
                    required_fields=["scene_layout", "panel_plan"],
                    review_output_field="plan_review",
                    review_history_output_field="plan_review_history",
                ),
                "outputs": results_schema,
            },
            {
                "id": "convert_storyboard_plan_to_image_prompt",
                "ref": "ai.parallel_deepseek_structured_json.v1",
                "inputs": {
                    **_parallel_storyboard_node_inputs(
                        "请把以下结构化分镜计划转换成完整分段画面内容提示词 {paragraph_text}",
                        passthrough_fields=[
                            "index",
                            "segment_title",
                            "paragraph_text",
                            "panel_count",
                            "present_characters",
                            "location",
                            "key_props",
                            "segment_assignment",
                            "scene_layout",
                            "panel_plan",
                        ],
                    ),
                    "items": {"from": "$nodes.review_and_refine_storyboard_plan.output.results"},
                },
                "outputs": results_schema,
            },
            {
                "id": "review_and_refine_image_prompt",
                "ref": "ai.storyboard_review_refine.v1",
                "inputs": _review_storyboard_node_inputs(
                    items_from="$nodes.convert_storyboard_plan_to_image_prompt.output.results",
                    review_prompt="请审查当前分段的 image_prompt {source}",
                    revision_prompt="请根据审查意见重新生成画面内容 {source}",
                    required_fields=["scene_layout", "panel_plan", "image_prompt"],
                    review_output_field="prompt_review",
                    review_history_output_field="prompt_review_history",
                ),
                "outputs": results_schema,
            },
        ],
        "edges": [
            {"from": "START", "to": "review_storyboard_image"},
            {"from": "review_storyboard_image", "to": "END"},
            {"from": "START", "to": "analyze_scene_layout"},
            {"from": "analyze_scene_layout", "to": "plan_storyboard_panels"},
            {"from": "plan_storyboard_panels", "to": "review_and_refine_storyboard_plan"},
            {
                "from": "review_and_refine_storyboard_plan",
                "to": "convert_storyboard_plan_to_image_prompt",
            },
            {
                "from": "convert_storyboard_plan_to_image_prompt",
                "to": "review_and_refine_image_prompt",
            },
            {"from": "review_and_refine_image_prompt", "to": "END"},
        ],
    }


def _parallel_storyboard_node_inputs(
    prompt_template: str,
    *,
    passthrough_fields: list[str],
) -> dict:
    return {
        "system": {"value": "仅返回合法 JSON。"},
        "items": {"value": []},
        "prompt_template": {"value": prompt_template},
        "passthrough_fields": {"value": passthrough_fields},
        "max_attempts": {"value": 1},
        "continue_on_item_error": {"value": False},
    }


def _review_storyboard_node_inputs(
    *,
    items_from: str,
    review_prompt: str,
    revision_prompt: str,
    required_fields: list[str],
    review_output_field: str,
    review_history_output_field: str,
) -> dict:
    return {
        "items": {"from": items_from},
        "review_system": {"value": "仅返回合法 JSON。"},
        "review_prompt_template": {"value": review_prompt},
        "revision_system": {"value": "仅返回合法 JSON。"},
        "revision_prompt_template": {"value": revision_prompt},
        "review_output_field": {"value": review_output_field},
        "review_history_output_field": {"value": review_history_output_field},
        "required_input_fields": {"value": required_fields},
        "max_revision_rounds": {"value": 0},
        "max_attempts": {"value": 1},
        "continue_on_item_error": {"value": False},
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


def _create_task_with_user_input(
    client: TestClient,
    *,
    headers: dict[str, str],
    project_id: str,
    contract: dict,
    input_data: dict,
) -> dict:
    create_response = client.post(
        "/api/tasks",
        json={"project_id": project_id, "contract": contract},
        headers=headers,
    )
    assert create_response.status_code == 200
    task = create_response.json()
    resume_response = client.post(
        f"/api/tasks/{task['task_id']}/interactions",
        json={
            "project_id": project_id,
            "node_id": "collect_user_input",
            "input": input_data,
        },
        headers=headers,
    )
    assert resume_response.status_code == 200
    return resume_response.json()


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
            "global",
            project["project_id"]
        ]


def test_auth_me_endpoint_returns_current_user(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        user = client.post(
            "/api/auth/register",
            json={"username": "session-user", "password": "secret-123"},
        ).json()
        headers = _auth_headers(client, username="session-user")

        response = client.get("/api/auth/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["user_id"] == user["user_id"]
    assert response.json()["username"] == "session-user"


def test_asset_draft_endpoint_uses_structured_llm_with_user_context(test_settings) -> None:
    class FakeDraftRouter(ChatModelRouter):
        def __init__(self) -> None:
            super().__init__()
            self.requests: list[ChatRequest] = []

        async def chat(self, request: ChatRequest) -> ChatResponse:
            self.requests.append(request)
            return ChatResponse(
                text=json.dumps(
                    {
                            "assets": [
                                {
                                    "asset_type": "character",
                                    "asset_name": "武松",
                                    "matched": False,
                                    "matched_asset_id": None,
                                "matched_asset_name": "",
                                "aliases": "行者",
                                "summary": "梁山好汉",
                                "character_status": "途经景阳冈",
                                "asset_tags": ["劲装短打", "哨棒"],
                                    "appearance_description": "头戴软巾，上身劲装短打，腰间束带，肩背利落，手持哨棒，保留行者武人气质和稳定识别特征。",
                                },
                                {
                                    "asset_type": "scene",
                                    "asset_name": "官兵船",
                                    "asset_tags": ["水上", "官船"],
                                    "matched": False,
                                "matched_asset_id": None,
                                "matched_asset_name": "",
                                "description": "官兵在水上押送使用的船只，甲板可站人，带低矮船舱、桅杆、缆绳和官府旗号。",
                                "location_type": "水上",
                                "time_of_day": "",
                            }
                        ],
                        "confidence": 0.86,
                        "reasoning": "根据用户描述和原文补全多个资产字段。",
                    },
                    ensure_ascii=False,
                ),
                model=request.model,
            )

    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "draft-user", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="draft-user")
        fake_router = FakeDraftRouter()
        app.state.services.asset_generations.prompt_draft_capability._model_router = fake_router  # noqa: SLF001

        response = client.post(
            "/api/assets/draft-from-description",
            headers=headers,
            json={
                "project_id": "global",
                "description": "增加一个拿哨棒的武松和官兵船",
                "script": "武松提着哨棒走过景阳冈。",
                "background": "水浒传",
                "current_assets": {
                    "characters": [
                        {
                            "asset_name": "不可信旧图",
                            "storage_uri": "local/private.png",
                            "public_url": "https://evil.test/leak.png",
                        }
                    ]
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["assets"][0]["asset_name"] == "武松"
    assert body["assets"][1]["asset_type"] == "scene"
    assert body["assets"][0]["matched"] is False
    assert fake_router.requests
    prompt = "\n".join(str(message.content) for message in fake_router.requests[0].messages)
    assert "用户描述的新资产需求" in prompt
    assert "武松提着哨棒" in prompt
    assert "local/private.png" not in prompt
    assert "https://evil.test/leak.png" not in prompt


def test_intelligent_asset_upload_enriches_metadata_and_type_tag(test_settings) -> None:
    class FakeUploadMetadataRouter(ChatModelRouter):
        def __init__(self) -> None:
            super().__init__()
            self.requests: list[ChatRequest] = []

        async def chat(self, request: ChatRequest) -> ChatResponse:
            self.requests.append(request)
            return ChatResponse(
                text=json.dumps(
                    {
                        "metadata": {
                            "type": "character",
                            "aliases": "豹子头",
                            "summary": "八十万禁军教头，后因奸臣陷害走上梁山。",
                            "relationships": "与鲁智深、柴进等梁山人物有交集。",
                            "character_status": "流落江湖阶段。",
                            "asset_tags": ["教头常服", "长枪"],
                            "appearance_description": "头戴软巾，上身整洁短袍，腰间束带，神态沉稳，带有武官气质。",
                            "description": "沉稳威严的武人形象。",
                            "location_type": "",
                            "time_of_day": "",
                            "category": "",
                            "related_character": "",
                        },
                        "confidence": 0.91,
                        "reasoning": "根据水浒传人物背景补全。",
                    },
                    ensure_ascii=False,
                ),
                model=request.model,
            )

    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "smart-upload-user", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="smart-upload-user")
        fake_router = FakeUploadMetadataRouter()
        app.state.services.asset_generations.asset_metadata_capability._model_router = fake_router  # noqa: SLF001

        response = client.post(
            "/api/assets/files/intelligent",
            headers=headers,
            data={
                "scope": "global",
                "name": "林冲",
                "asset_type": "character",
                "world_background": "水浒传",
                "publish": "true",
            },
            files={"file": ("linchong.png", b"fake image", "image/png")},
        )
        asset_id = response.json()["asset"]["asset_id"]
        tags_response = client.get(f"/api/assets/{asset_id}/tags", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["asset"]["name"] == "林冲"
    assert "storage_uri" not in body["asset"]
    assert body["asset"]["content_url"] == f"/api/assets/{asset_id}/content"
    assert body["asset"]["thumbnail_url"] == f"/api/assets/{asset_id}/thumbnail"
    assert body["asset"]["metadata"]["type"] == "character"
    assert body["asset"]["metadata"]["summary"].startswith("八十万禁军教头")
    assert body["confidence"] == 0.91
    assert tags_response.status_code == 200
    assert [tag["name"] for tag in tags_response.json()["items"]] == ["角色"]
    prompt = "\n".join(str(message.content) for message in fake_router.requests[0].messages)
    assert "林冲" in prompt
    assert "水浒传" in prompt


def test_episode_metadata_text_asset_gets_type_tag_on_create_and_update(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "episode-metadata-user", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="episode-metadata-user")

        create_response = client.post(
            "/api/assets/text",
            headers=headers,
            json={
                "scope": "global",
                "name": "23、私放晁天王",
                "text": "集剧情概括、原剧本内容和资产目录。",
                "metadata": {"type": "episode_metadata"},
            },
        )
        asset_id = create_response.json()["asset_id"]
        created_tags_response = client.get(f"/api/assets/{asset_id}/tags", headers=headers)
        text_update_response = client.put(
            f"/api/assets/{asset_id}/text",
            headers=headers,
            json={
                "name": "23、私放晁天王",
                "text": "修改后的集剧情概括、原剧本内容和资产目录。",
                "metadata": {"type": "episode_metadata", "episode_name": "私放晁天王"},
            },
        )
        content_response = client.get(f"/api/assets/{asset_id}/content", headers=headers)

        normal_response = client.post(
            "/api/assets/text",
            headers=headers,
            json={
                "scope": "global",
                "name": "普通文字资产",
                "text": "普通内容。",
                "metadata": {},
            },
        )
        normal_id = normal_response.json()["asset_id"]
        update_response = client.patch(
            f"/api/assets/{normal_id}",
            headers=headers,
            json={
                "name": "普通文字资产",
                "metadata": {"type": "集信息资产"},
            },
        )
        updated_tags_response = client.get(f"/api/assets/{normal_id}/tags", headers=headers)

    assert create_response.status_code == 200
    assert created_tags_response.status_code == 200
    assert [tag["name"] for tag in created_tags_response.json()["items"]] == ["集元数据"]
    assert text_update_response.status_code == 200
    assert text_update_response.json()["metadata"]["episode_name"] == "私放晁天王"
    assert content_response.status_code == 200
    assert content_response.text == "修改后的集剧情概括、原剧本内容和资产目录。"
    assert normal_response.status_code == 200
    assert update_response.status_code == 200
    assert [tag["name"] for tag in updated_tags_response.json()["items"]] == ["集元数据"]


def test_asset_generate_image_endpoint_returns_single_generated_image(test_settings) -> None:
    class FakeImageRouter(ChatModelRouter):
        def __init__(self) -> None:
            super().__init__()
            self.requests: list[ChatRequest] = []

        async def chat(self, request: ChatRequest) -> ChatResponse:
            self.requests.append(request)
            return ChatResponse(
                text="https://cdn.example.com/generated-linchong.png",
                model=request.model,
                metadata={"task_id": "rh-1", "variant": "image-to-image"},
            )

    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "image-user", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="image-user")
        fake_router = FakeImageRouter()
        app.state.services.asset_generations.image_generation_capability._model_router = fake_router  # noqa: SLF001

        response = client.post(
            "/api/assets/generate-image",
            headers=headers,
            json={
                "project_id": "global",
                "prompt_result": {
                    "full_name": "林冲_囚服",
                    "prompt": "身着囚服，头戴毡笠。",
                    "reference_image_ref": {
                        "kind": "data_uri",
                        "data": "data:image/png;base64,aW1hZ2UtYnl0ZXM=",
                    },
                },
                "aspect_ratio": "1:1",
                "resolution": "2k",
            },
        )
        body = response.json()
        status_response = client.get(
            f"/api/assets/generate-image/{body['generation_id']}",
            headers=headers,
        )

    assert response.status_code == 200
    assert body["generation_id"].startswith("asset_generation_")
    assert body["status"] in {"queued", "running", "succeeded"}
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["status"] == "succeeded"
    assert status_body["result"]["full_name"] == "林冲_囚服"
    assert status_body["result"]["image_url"] == "https://cdn.example.com/generated-linchong.png"
    assert status_body["result"]["source"] == "ai_generated"
    assert status_body["result"]["runninghub_task_id"] == "rh-1"
    assert fake_router.requests
    assert fake_router.requests[0].metadata["images"] == [
        "data:image/png;base64,aW1hZ2UtYnl0ZXM="
    ]


def test_storyboard_panel_prompt_regeneration_runs_full_segment_chain(test_settings) -> None:
    class FakeStoryboardRouter(ChatModelRouter):
        def __init__(self) -> None:
            super().__init__()
            self.requests: list[ChatRequest] = []
            self.responses = [
                {
                    "scene_layout": {
                        "location_summary": "机密房内方桌议事",
                        "spatial_zones": ["前景桌角", "中景众公差", "背景墙面"],
                        "layout_constraints": ["方桌始终位于画面中心附近"],
                    }
                },
                {
                    "think": "完整推理过程：两格表现密议压力。",
                    "segment_title": "机密房密议",
                    "panel_plan": {
                        "panel_count": 2,
                        "page_layout": "两格横向推进",
                        "panels": [
                            {
                                "panel_index": 1,
                                "narrative_purpose": "建立机密房空间",
                                "characters": ["何涛", "众公差"],
                                "visible_props": ["方桌"],
                                "frame_content": "何涛进入机密房。",
                            },
                            {
                                "panel_index": 2,
                                "narrative_purpose": "表现众人围桌密议的压迫感",
                                "characters": ["何涛", "众公差"],
                                "visible_props": ["方桌"],
                                "frame_content": "何涛与众公差围着方桌讨论。",
                            }
                        ],
                    },
                },
                {
                    "think": "完整推理过程：分镜计划符合当前段落。",
                    "passed": True,
                    "issues": [],
                    "revision_instructions": "",
                    "revision_summary": "通过",
                },
                {
                    "think": "完整推理过程：按两格计划转换为画面内容。",
                    "image_prompt": "何涛与众公差在机密房内围着方桌密议。一共有2格。第1格何涛进入机密房。第2格出现何涛和众公差。整页为两格横向推进，方桌占据中景中心，何涛侧对镜头，众公差围在桌边，背景墙面压低空间，光线集中在桌面形成紧张气氛。",
                },
                {
                    "think": "完整推理过程：画面提示词忠于分镜计划。",
                    "passed": True,
                    "issues": [],
                    "revision_instructions": "",
                    "revision_summary": "通过",
                },
            ]

        async def chat(self, request: ChatRequest) -> ChatResponse:
            self.requests.append(request)
            return ChatResponse(
                text=json.dumps(self.responses.pop(0), ensure_ascii=False),
                model=request.model,
                metadata={"provider": request.provider},
            )

    app = create_app(settings=replace(test_settings, workflow_dir=Path("workflows")))
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "storyboard-prompt-user", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="storyboard-prompt-user")
        fake_router = FakeStoryboardRouter()
        app.state.services.node_registry.get("ai.parallel_deepseek_structured_json.v1")._model_router = fake_router  # noqa: SLF001
        app.state.services.node_registry.get("ai.storyboard_review_refine.v1")._model_router = fake_router  # noqa: SLF001

        task_response = client.post(
            "/api/tasks",
            headers=headers,
            json={
                "project_id": "global",
                "contract": _storyboard_prompt_interaction_contract(),
            },
        )
        task = task_response.json()
        response = client.post(
            f"/api/tasks/{task['task_id']}/interactions/storyboard-panel-prompt",
            headers=headers,
            json={
                "project_id": "global",
                "node_id": "review_storyboard_image",
                "card": {
                    "card_id": "segment-0",
                    "segment_index": 0,
                    "panel_index": 0,
                    "reference_images": [
                        {
                            "label": "何涛",
                            "asset_type": "character",
                            "asset_name": "何涛",
                            "asset_tags": ["官差"],
                            "image_ref": {
                                "kind": "data_uri",
                                "data": "data:image/png;base64,aGV0YW8=",
                                "role": "reference",
                            },
                            "source": "asset",
                        },
                        {
                            "label": "众公差",
                            "asset_type": "character",
                            "asset_name": "众公差",
                            "image_ref": {
                                "kind": "data_uri",
                                "data": "data:image/png;base64,Z29uZ2NoYWk=",
                                "role": "reference",
                            },
                            "source": "asset",
                        },
                    ],
                },
                "item": {
                    "index": 0,
                    "paragraph_text": "何涛来到机密房里和众公差商议。",
                    "panel_count": "2",
                    "present_characters": ["何涛", "众公差"],
                    "location": "机密房",
                    "key_props": ["方桌"],
                    "segment_assignment": {"segment_index": 0, "characters": [], "prop_assets": []},
                },
                "shared_context": {
                    "world_background": "水浒传官府缉捕情节。",
                    "full_script": "何涛来到机密房里和众公差商议。",
                    "prompt_rules": {
                        "material_rule": "不写材质。",
                        "enrich_rule": "补足空间关系。",
                        "material_thinking": "不讨论材质。",
                        "enrich_thinking": "检查空间关系。",
                    },
                },
            },
        )
        detail_response = client.get(
            f"/api/tasks/{task['task_id']}",
            headers=headers,
            params={"project_id": "global"},
        )

    assert task_response.status_code == 200
    assert task["status"] == "waiting"
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["segment_description"]["segment_title"] == "机密房密议"
    assert body["segment_description"]["panel_plan"]["panel_count"] == 2
    assert body["segment_description"]["prompt_review"]["passed"] is True
    assert "何涛（参考图1）与众公差（参考图2）在机密房内围着方桌密议" in body["card"]["prompt"]
    assert "图1是角色何涛" in body["card"]["prompt"]
    assert "图2是角色众公差" in body["card"]["prompt"]
    assert "何涛（参考图1）" in body["card"]["prompt"]
    assert "众公差（参考图2）" in body["card"]["prompt"]
    assert "用户手动指定目标分格数为 2" in fake_router.requests[1].messages[-1].content
    assert "panel_plan.panel_count 等于 2" in fake_router.requests[2].messages[-1].content
    assert detail_response.status_code == 200
    detail = detail_response.json()
    event_types = [event["event_type"] for event in detail["events"]]
    assert "node_ai_interaction_started" in event_types
    assert "node_ai_interaction_succeeded" in event_types
    assert "node_draft_saved" in event_types
    waiting_execution = next(
        execution
        for execution in detail["node_executions"]
        if execution["node_id"] == "review_storyboard_image"
    )
    assert waiting_execution["input_snapshot"]["ai_generated_storyboard_panel_prompt"]["card"]["card_id"] == "segment-0"
    assert len(fake_router.requests) == 5
    prompts = ["\n".join(str(message.content) for message in request.messages) for request in fake_router.requests]
    assert "请分析当前段落的实际场景布局" in prompts[0]
    assert "请为当前段落规划一页漫画分镜" in prompts[1]
    assert "请用提问方式审查当前段落的结构化分镜计划" in prompts[2]
    assert "请把以下结构化分镜计划转换成完整分段画面内容提示词" in prompts[3]
    assert "请审查当前分段的 image_prompt" in prompts[4]
    assert all(request.metadata == {"response_format": {"type": "json_object"}} for request in fake_router.requests)


def test_global_project_is_default_shared_project_and_supports_user_tasks(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        alice = client.post(
            "/api/auth/register",
            json={"username": "global-alice", "password": "secret-123"},
        ).json()
        alice_headers = _auth_headers(client, username="global-alice")
        client.post(
            "/api/auth/register",
            json={"username": "global-bob", "password": "secret-123"},
        )
        bob_headers = _auth_headers(client, username="global-bob")

        alice_projects_response = client.get("/api/projects", headers=alice_headers)
        bob_projects_response = client.get("/api/projects", headers=bob_headers)
        task = _create_task_with_user_input(
            client,
            headers=alice_headers,
            project_id="global",
            contract=_echo_contract(),
            input_data={"topic": "global task"},
        )
        alice_tasks_response = client.get(
            "/api/tasks",
            params={"project_id": "global"},
            headers=alice_headers,
        )
        bob_tasks_response = client.get(
            "/api/tasks",
            params={"project_id": "global"},
            headers=bob_headers,
        )

    assert alice_projects_response.status_code == 200
    assert bob_projects_response.status_code == 200
    assert alice_projects_response.json()["items"][0]["project_id"] == "global"
    assert alice_projects_response.json()["items"][0]["name"] == "全局项目"
    assert bob_projects_response.json()["items"][0]["project_id"] == "global"

    assert task["project_id"] == "global"
    assert task["user_id"] == alice["user_id"]

    assert alice_tasks_response.status_code == 200
    assert [item["task_id"] for item in alice_tasks_response.json()["items"]] == [
        task["task_id"]
    ]
    assert bob_tasks_response.status_code == 200
    assert bob_tasks_response.json()["items"] == []


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
        exact_name_response = client.get(
            "/api/assets/search",
            params={
                "scope": "project",
                "project_id": project["project_id"],
                "names": "Character Brief,Missing Asset",
                "limit": 2,
            },
            headers=headers,
        )

    assert search_response.status_code == 200
    result = search_response.json()
    assert result["total"] == 1
    assert result["items"][0]["asset_id"] == asset["asset_id"]
    assert exact_name_response.status_code == 200
    exact_name_result = exact_name_response.json()
    assert exact_name_result["total"] == 1
    assert exact_name_result["items"][0]["asset_id"] == asset["asset_id"]


def test_asset_collection_update_and_delete_endpoints(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "collection-editor", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="collection-editor")
        project = client.post(
            "/api/projects",
            json={"name": "Collection Project"},
            headers=headers,
        ).json()
        parent_response = client.post(
            "/api/assets/collections",
            json={
                "scope": "project",
                "project_id": project["project_id"],
                "name": "old folder",
            },
            headers=headers,
        )
        assert parent_response.status_code == 200
        parent = parent_response.json()
        child_response = client.post(
            "/api/assets/collections",
            json={
                "scope": "project",
                "project_id": project["project_id"],
                "parent_id": parent["collection_id"],
                "name": "child folder",
            },
            headers=headers,
        )
        assert child_response.status_code == 200

        rename_response = client.patch(
            f"/api/assets/collections/{parent['collection_id']}",
            json={"name": "renamed folder"},
            headers=headers,
        )
        list_after_rename = client.get(
            "/api/assets/collections",
            params={"scope": "project", "project_id": project["project_id"]},
            headers=headers,
        )
        delete_response = client.delete(
            f"/api/assets/collections/{parent['collection_id']}",
            headers=headers,
        )
        list_after_delete = client.get(
            "/api/assets/collections",
            params={"scope": "project", "project_id": project["project_id"]},
            headers=headers,
        )

    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "renamed folder"
    assert [item["name"] for item in list_after_rename.json()["items"]] == ["renamed folder", "child folder"]
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}
    assert list_after_delete.json()["items"] == []


def test_asset_tag_update_and_delete_endpoints(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "tag-editor", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="tag-editor")
        project = client.post(
            "/api/projects",
            json={"name": "Tag Project"},
            headers=headers,
        ).json()
        create_response = client.post(
            "/api/assets/tags",
            json={
                "scope": "project",
                "project_id": project["project_id"],
                "name": "old tag",
            },
            headers=headers,
        )
        assert create_response.status_code == 200
        tag = create_response.json()

        rename_response = client.patch(
            f"/api/assets/tags/{tag['tag_id']}",
            json={"name": "renamed tag"},
            headers=headers,
        )
        list_after_rename = client.get(
            "/api/assets/tags",
            params={"scope": "project", "project_id": project["project_id"]},
            headers=headers,
        )
        delete_response = client.delete(
            f"/api/assets/tags/{tag['tag_id']}",
            headers=headers,
        )
        list_after_delete = client.get(
            "/api/assets/tags",
            params={"scope": "project", "project_id": project["project_id"]},
            headers=headers,
        )

    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "renamed tag"
    assert [item["name"] for item in list_after_rename.json()["items"]] == ["renamed tag"]
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}
    assert list_after_delete.json()["items"] == []


def test_asset_tag_attach_detach_and_empty_delete_endpoints(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "asset-tagger", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="asset-tagger")
        project = client.post(
            "/api/projects",
            json={"name": "Asset Tag Project"},
            headers=headers,
        ).json()
        tag = client.post(
            "/api/assets/tags",
            json={"scope": "project", "project_id": project["project_id"], "name": "角色"},
            headers=headers,
        ).json()
        asset = client.post(
            "/api/assets/text",
            json={
                "scope": "project",
                "project_id": project["project_id"],
                "name": "hero notes",
                "text": "hero profile",
            },
            headers=headers,
        ).json()

        attach_response = client.post(
            f"/api/assets/{asset['asset_id']}/tags/{tag['tag_id']}",
            headers=headers,
        )
        tags_after_attach = client.get(
            "/api/assets/tags",
            params={"scope": "project", "project_id": project["project_id"]},
            headers=headers,
        )
        delete_non_empty_response = client.delete(
            f"/api/assets/tags/{tag['tag_id']}",
            headers=headers,
        )
        current_tags_response = client.get(
            f"/api/assets/{asset['asset_id']}/tags",
            headers=headers,
        )
        detach_response = client.delete(
            f"/api/assets/{asset['asset_id']}/tags/{tag['tag_id']}",
            headers=headers,
        )
        delete_empty_response = client.delete(
            f"/api/assets/tags/{tag['tag_id']}",
            headers=headers,
        )

    assert attach_response.status_code == 200
    assert [item["tag_id"] for item in attach_response.json()["items"]] == [tag["tag_id"]]
    assert tags_after_attach.json()["items"][0]["asset_count"] == 1
    assert delete_non_empty_response.status_code == 400
    assert delete_non_empty_response.json()["error"]["code"] == "asset_tag_not_empty"
    assert [item["tag_id"] for item in current_tags_response.json()["items"]] == [tag["tag_id"]]
    assert detach_response.status_code == 200
    assert detach_response.json()["items"] == []
    assert delete_empty_response.status_code == 200


def test_file_asset_upload_returns_public_url_and_searches_by_tag(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "asset-uploader", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="asset-uploader")
        project = client.post(
            "/api/projects",
            json={"name": "Upload Project"},
            headers=headers,
        ).json()
        tag_response = client.post(
            "/api/assets/tags",
            json={"scope": "project", "project_id": project["project_id"], "name": "主角"},
            headers=headers,
        )
        assert tag_response.status_code == 200
        tag = tag_response.json()

        upload_response = client.post(
            "/api/assets/files",
            data={
                "scope": "project",
                "project_id": project["project_id"],
                "name": "hero.png",
                "tag_ids": tag["tag_id"],
                "publish": "true",
            },
            files={"file": ("hero.png", b"fake image", "image/png")},
            headers=headers,
        )

        assert upload_response.status_code == 200
        asset = upload_response.json()
        assert asset["metadata"]["public_url"]

        search_response = client.get(
            "/api/assets/search",
            params={
                "scope": "project",
                "project_id": project["project_id"],
                "tag_ids": tag["tag_id"],
            },
            headers=headers,
        )
        assert search_response.status_code == 200
        assert search_response.json()["items"][0]["asset_id"] == asset["asset_id"]


def test_asset_name_can_be_updated(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "asset-renamer", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="asset-renamer")
        upload_response = client.post(
            "/api/assets/files",
            data={
                "scope": "global",
                "name": "source-file.png",
                "publish": "false",
            },
            files={"file": ("source-file.png", b"fake image", "image/png")},
            headers=headers,
        )
        asset = upload_response.json()

        rename_response = client.patch(
            f"/api/assets/{asset['asset_id']}",
            json={"name": "主角立绘"},
            headers=headers,
        )
        search_response = client.get(
            "/api/assets/search",
            params={"scope": "global", "keyword": "主角"},
            headers=headers,
        )
        invalid_response = client.patch(
            f"/api/assets/{asset['asset_id']}",
            json={"name": "   "},
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "主角立绘"
    assert search_response.status_code == 200
    assert search_response.json()["items"][0]["asset_id"] == asset["asset_id"]
    assert invalid_response.status_code == 400
    assert invalid_response.json()["error"]["code"] == "asset_name_required"


def test_asset_file_can_be_replaced(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "asset-replacer", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="asset-replacer")
        upload_response = client.post(
            "/api/assets/files",
            data={
                "scope": "global",
                "name": "template.png",
                "metadata_json": '{"appearance_description": "旧图描述"}',
                "publish": "false",
            },
            files={"file": ("template.png", b"old image", "image/png")},
            headers=headers,
        )
        asset = upload_response.json()

        replace_response = client.put(
            f"/api/assets/{asset['asset_id']}/file",
            files={"file": ("template.jpg", b"new image", "image/jpeg")},
            headers=headers,
        )
        content_response = client.get(
            f"/api/assets/{asset['asset_id']}/content",
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert replace_response.status_code == 200
    assert replace_response.json()["asset_id"] == asset["asset_id"]
    assert replace_response.json()["name"] == "template.png"
    assert replace_response.json()["mime_type"] == "image/jpeg"
    assert replace_response.json()["metadata"]["appearance_description"] == "旧图描述"
    assert content_response.status_code == 200
    assert content_response.content == b"new image"
    assert content_response.headers["content-type"].startswith("image/jpeg")


def test_asset_thumbnail_endpoint_generates_cached_png(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "asset-thumbnailer", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="asset-thumbnailer")
        upload_response = client.post(
            "/api/assets/files",
            data={
                "scope": "global",
                "name": "thumbnail-source.png",
                "publish": "false",
            },
            files={"file": ("thumbnail-source.png", PNG_1X1, "image/png")},
            headers=headers,
        )
        asset = upload_response.json()

        first_response = client.get(
            f"/api/assets/{asset['asset_id']}/thumbnail",
            params={"size": 128},
            headers=headers,
        )
        second_response = client.get(
            f"/api/assets/{asset['asset_id']}/thumbnail",
            params={"size": 128},
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert first_response.status_code == 200
    assert first_response.headers["content-type"].startswith("image/png")
    assert first_response.headers["x-asset-thumbnail-cache"] == "miss"
    assert first_response.content.startswith(b"\x89PNG")
    assert second_response.status_code == 200
    assert second_response.headers["x-asset-thumbnail-cache"] == "hit"
    assert second_response.content == first_response.content


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

        task = _create_task_with_user_input(
            client,
            headers=headers,
            project_id=project["project_id"],
            contract=_echo_contract(),
            input_data={"topic": "API smoke"},
        )
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


def test_create_task_rejects_pre_task_business_input_data(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "task-input-blocked", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="task-input-blocked")
        project = client.post(
            "/api/projects",
            json={"name": "Task Input Block Project"},
            headers=headers,
        ).json()
        response = client.post(
            "/api/tasks",
            json={
                "project_id": project["project_id"],
                "contract": _echo_contract(),
                "input_data": {"topic": "blocked"},
            },
            headers=headers,
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_failed"


def test_task_list_detail_and_stream_return_project_scoped_runtime_data(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "task-list-owner", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="task-list-owner")
        first_project = client.post(
            "/api/projects",
            json={"name": "First Task Project"},
            headers=headers,
        ).json()
        second_project = client.post(
            "/api/projects",
            json={"name": "Second Task Project"},
            headers=headers,
        ).json()
        contract = _echo_contract()

        first_task = _create_task_with_user_input(
            client,
            headers=headers,
            project_id=first_project["project_id"],
            contract=contract,
            input_data={"topic": "first"},
        )
        second_task = _create_task_with_user_input(
            client,
            headers=headers,
            project_id=second_project["project_id"],
            contract=contract,
            input_data={"topic": "second"},
        )

        list_response = client.get(
            "/api/tasks",
            params={"project_id": first_project["project_id"]},
            headers=headers,
        )
        detail_response = client.get(
            f"/api/tasks/{first_task['task_id']}",
            params={"project_id": first_project["project_id"]},
            headers=headers,
        )
        stream_response = client.get(
            f"/api/tasks/{first_task['task_id']}/stream",
            params={"project_id": first_project["project_id"]},
            headers=headers,
        )

    assert list_response.status_code == 200
    assert [item["task_id"] for item in list_response.json()["items"]] == [
        first_task["task_id"]
    ]
    assert second_task["task_id"] not in {
        item["task_id"] for item in list_response.json()["items"]
    }

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["workflow_snapshot"] == contract
    assert detail["node_attempts"]["collect_user_input"][0]["attempt"] == 1
    assert detail["node_attempts"]["echo"][0]["attempt"] == 1
    assert detail["node_attempts"]["echo"][0]["node_execution_id"] == detail["task"][
        "current_view"
    ]["active_node_outputs"]["echo"]

    assert stream_response.status_code == 200
    assert stream_response.headers["content-type"].startswith("text/event-stream")
    assert "event: task_created\n" in stream_response.text
    assert "event: task_succeeded\n" in stream_response.text


def test_task_debug_export_returns_downloadable_execution_history(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "task-debug-exporter", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="task-debug-exporter")
        project = client.post(
            "/api/projects",
            json={"name": "Debug Export Project"},
            headers=headers,
        ).json()
        contract = _approval_contract()
        task = _create_task_with_user_input(
            client,
            headers=headers,
            project_id=project["project_id"],
            contract=contract,
            input_data={"topic": "needs approval"},
        )

        draft_response = client.put(
            f"/api/tasks/{task['task_id']}/interactions/draft",
            json={
                "project_id": project["project_id"],
                "node_id": "review",
                "input": {"decision": "approve", "api_key": "sk-debug-secret"},
            },
            headers=headers,
        )
        approve_response = client.post(
            f"/api/tasks/{task['task_id']}/interactions",
            json={
                "project_id": project["project_id"],
                "node_id": "review",
                "input": {"decision": "approve"},
            },
            headers=headers,
        )
        rerun_response = client.post(
            f"/api/tasks/{task['task_id']}/nodes/review/rerun",
            json={
                "project_id": project["project_id"],
                "rerun_revision_note": "重新检查审批节点。",
            },
            headers=headers,
        )
        export_response = client.get(
            f"/api/tasks/{task['task_id']}/debug-export",
            params={"project_id": project["project_id"]},
            headers=headers,
        )

    assert draft_response.status_code == 200
    assert approve_response.status_code == 200
    assert rerun_response.status_code == 200
    assert rerun_response.json()["status"] == "waiting"
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("application/json")
    assert "attachment" in export_response.headers["content-disposition"]
    assert export_response.headers["content-disposition"].endswith(".json\"")

    payload = export_response.json()
    assert {
        "export_version",
        "generated_at",
        "task",
        "workflow_snapshot",
        "node_executions",
        "node_attempts",
        "events",
    } <= set(payload)
    assert payload["export_version"] == "task_debug_export.v1"
    assert payload["task"]["task_id"] == task["task_id"]
    assert payload["workflow_snapshot"] == contract
    statuses = {execution["status"] for execution in payload["node_executions"]}
    assert {"succeeded", "superseded", "waiting"} <= statuses
    assert [attempt["status"] for attempt in payload["node_attempts"]["review"]] == [
        "superseded",
        "waiting",
    ]
    draft_events = [
        event for event in payload["events"] if event["event_type"] == "node_draft_saved"
    ]
    assert draft_events
    draft_payload = draft_events[-1]["payload"]
    assert draft_payload["input_patch"] == {
        "decision": "approve",
        "api_key": "***redacted***",
    }
    assert draft_payload["input_snapshot_after"]["decision"] == "approve"
    assert draft_payload["input_snapshot_after"]["api_key"] == "***redacted***"


def test_delete_task_archives_project_scoped_runtime_data(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "task-delete-owner", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="task-delete-owner")
        project = client.post(
            "/api/projects",
            json={"name": "Delete Task Project"},
            headers=headers,
        ).json()
        task = _create_task_with_user_input(
            client,
            headers=headers,
            project_id=project["project_id"],
            contract=_echo_contract(),
            input_data={"topic": "delete me"},
        )

        delete_response = client.delete(
            f"/api/tasks/{task['task_id']}",
            params={"project_id": project["project_id"]},
            headers=headers,
        )
        list_response = client.get(
            "/api/tasks",
            params={"project_id": project["project_id"]},
            headers=headers,
        )
        detail_response = client.get(
            f"/api/tasks/{task['task_id']}",
            params={"project_id": project["project_id"]},
            headers=headers,
        )

    archived_rows = asyncio.run(_fetch_archived_task_rows(test_settings.database_path, task["task_id"]))

    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "task_id": task["task_id"]}
    assert list_response.status_code == 200
    assert list_response.json()["items"] == []
    assert detail_response.status_code == 404
    assert detail_response.json()["error"]["code"] == "task_not_found"
    assert archived_rows["task_status"] == "archived"
    assert archived_rows["node_executions"] == 2
    assert archived_rows["task_events"] > 0
    assert "task_archived" in archived_rows["event_types"]


def test_task_interactions_endpoint_resumes_waiting_task(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "task-interactor", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="task-interactor")
        project = client.post(
            "/api/projects",
            json={"name": "Interaction Project"},
            headers=headers,
        ).json()
        task = _create_task_with_user_input(
            client,
            headers=headers,
            project_id=project["project_id"],
            contract=_approval_contract(),
            input_data={"topic": "needs approval"},
        )

        response = client.post(
            f"/api/tasks/{task['task_id']}/interactions",
            json={
                "project_id": project["project_id"],
                "node_id": "review",
                "input": {"decision": "approve"},
            },
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"


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
        task = _create_task_with_user_input(
            client,
            headers=headers,
            project_id=project["project_id"],
            contract=_echo_contract(),
            input_data={"topic": "query"},
        )

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

        task = _create_task_with_user_input(
            client,
            headers=owner_headers,
            project_id=owner_project["project_id"],
            contract=_echo_contract(),
            input_data={"topic": "private"},
        )

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
      required:
        - topic
      properties:
        topic:
          type: string
  - id: echo
    ref: tool.echo.v1
    inputs:
      topic:
        from: $nodes.collect_user_input.output.topic
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
    (nested_dir / "project-only.workflow.yaml").write_text(
        _workflow_yaml(
            workflow_id="project-only-sample",
            name="Project Only Sample",
            scope="project",
            project_id="project-only",
        ),
        encoding="utf-8",
    )
    app = create_app(settings=replace(test_settings, workflow_dir=workflow_dir))

    with TestClient(app) as client:
        client.post("/api/auth/register", json={"username": "alice", "password": "secret-123"})
        headers = _auth_headers(client, username="alice")
        response = client.get("/api/workflows", headers=headers)

    assert response.status_code == 200
    workflow_ids = {item["workflow"]["id"] for item in response.json()["items"]}
    assert "nested-sample" in workflow_ids
    assert "project-only-sample" not in workflow_ids


def test_workflows_endpoint_filters_workflows_for_current_project(test_settings) -> None:
    workflow_dir = test_settings.workflow_dir / "global"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "global.workflow.yaml").write_text(
        _workflow_yaml(workflow_id="global-sample", name="Global Sample", scope="global"),
        encoding="utf-8",
    )
    (workflow_dir / "project-a.workflow.yaml").write_text(
        _workflow_yaml(
            workflow_id="project-a-sample",
            name="Project A Sample",
            scope="project",
            project_id="project-a",
        ),
        encoding="utf-8",
    )
    (workflow_dir / "project-b.workflow.yaml").write_text(
        _workflow_yaml(
            workflow_id="project-b-sample",
            name="Project B Sample",
            scope="project",
            project_id="project-b",
        ),
        encoding="utf-8",
    )
    asyncio.run(_insert_user_project(test_settings.database_path, user_id="user-a", project_id="project-a"))
    app = create_app(settings=replace(test_settings, workflow_dir=test_settings.workflow_dir))

    with TestClient(app) as client:
        client.app.state.services.access_tokens["token-a"] = "user-a"
        response = client.get(
            "/api/workflows",
            params={"project_id": "project-a"},
            headers={"Authorization": "Bearer token-a"},
        )

    assert response.status_code == 200
    workflow_ids = {item["workflow"]["id"] for item in response.json()["items"]}
    assert workflow_ids == {"global-sample", "project-a-sample"}


def test_workflows_endpoint_accepts_default_global_project(test_settings) -> None:
    workflow_dir = test_settings.workflow_dir / "global"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "global.workflow.yaml").write_text(
        _workflow_yaml(workflow_id="global-sample", name="Global Sample", scope="global"),
        encoding="utf-8",
    )
    app = create_app(settings=replace(test_settings, workflow_dir=test_settings.workflow_dir))

    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "global-workflow-user", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="global-workflow-user")
        response = client.get(
            "/api/workflows",
            params={"project_id": "global"},
            headers=headers,
        )

    assert response.status_code == 200
    workflow_ids = {item["workflow"]["id"] for item in response.json()["items"]}
    assert workflow_ids == {"global-sample"}


def test_request_validation_errors_use_standard_error_shape(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/register",
            json={"username": "bad-password-input", "password": 123},
        )

    assert response.status_code == 422
    body = response.json()
    assert "detail" not in body
    assert body["error"]["code"] == "request_validation_failed"
    assert body["error"]["message"]
    assert body["error"]["details"]
    assert body["error"]["details"]["errors"][0]["loc"] == ["body", "password"]
    assert "input" not in body["error"]["details"]["errors"][0]


async def _fetch_archived_task_rows(database_path, task_id: str) -> dict:
    async with connect_db(database_path) as db:
        task_row = await _fetch_one(
            db,
            "select status from tasks where task_id = ?",
            (task_id,),
        )
        execution_row = await _fetch_one(
            db,
            "select count(*) as total from node_executions where task_id = ?",
            (task_id,),
        )
        event_row = await _fetch_one(
            db,
            "select count(*) as total from task_events where task_id = ?",
            (task_id,),
        )
        event_cursor = await db.execute(
            "select event_type from task_events where task_id = ? order by rowid asc",
            (task_id,),
        )
        try:
            event_rows = await event_cursor.fetchall()
        finally:
            await event_cursor.close()
    return {
        "task_status": task_row["status"] if task_row is not None else None,
        "node_executions": int(execution_row["total"]) if execution_row is not None else 0,
        "task_events": int(event_row["total"]) if event_row is not None else 0,
        "event_types": [row["event_type"] for row in event_rows],
    }


async def _fetch_one(db, query: str, parameters: tuple):
    cursor = await db.execute(query, parameters)
    try:
        return await cursor.fetchone()
    finally:
        await cursor.close()


def _workflow_yaml(*, workflow_id: str, name: str, scope: str, project_id: str | None = None) -> str:
    project_line = f"  project_id: {project_id}\n" if project_id else ""
    return f"""
workflow:
  id: {workflow_id}
  version: 1.0.0
  scope: {scope}
{project_line}  name: {name}
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
      required:
        - topic
      properties:
        topic:
          type: string
  - id: echo
    ref: tool.echo.v1
    inputs:
      topic:
        from: $nodes.collect_user_input.output.topic
    outputs:
      type: object
edges:
  - from: START
    to: collect_user_input
  - from: collect_user_input
    to: echo
  - from: echo
    to: END
""".lstrip()


async def _insert_user_project(database_path, *, user_id: str, project_id: str) -> None:
    await migrate(database_path)
    async with connect_db(database_path) as db:
        await db.execute(
            """
            insert into users (user_id, username, password_hash, status, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (user_id, "workflow-owner", "not-used", "active", "2026-05-27T00:00:00Z", "2026-05-27T00:00:00Z"),
        )
        await db.execute(
            """
            insert into projects (project_id, owner_user_id, name, description, status, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, user_id, "Project A", None, "active", "2026-05-27T00:00:00Z", "2026-05-27T00:00:00Z"),
        )
