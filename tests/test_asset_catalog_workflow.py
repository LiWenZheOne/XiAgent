from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite
import pytest

from xiagent.core.errors import ValidationError
from xiagent.core.schemas import validate_json_value
from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes import build_node_registry
from xiagent.nodes.ai.deepseek_structured_json import DeepSeekStructuredJsonNode
from xiagent.nodes.ai.parallel_deepseek_structured_json import (
    ParallelDeepSeekStructuredJsonNode,
)
from xiagent.nodes.ai.runninghub_image import RunningHubImageToImageNode
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.system.user_input import SystemUserInputNode
from xiagent.nodes.tools.asset_lookup import AssetLookupNode
from xiagent.nodes.tools.create_text_asset import CreateTextAssetNode
from xiagent.nodes.tools.enrich_characters import EnrichCharactersNode
from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.testing import WorkflowTestBuilder
from xiagent.workflows.testing.console import ConsoleIO
from xiagent.workflows.testing.runner import WorkflowTestRunner
from xiagent.workflows.validator import validate_workflow_contract

ASSET_CATALOG_WORKFLOW_PATH = Path("workflows/global/asset_catalog.workflow.yaml")


async def test_create_text_asset_requires_asset_service_context() -> None:
    node = CreateTextAssetNode()

    with pytest.raises(ValidationError) as exc_info:
        await node.run(
            None,
            {
                "scope": "project",
                "project_id": "project_1",
                "name": "story seed",
                "text": "content",
            },
        )

    assert exc_info.value.code == "create_text_asset_no_context"


def test_asset_catalog_workflow_contract_structure(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)

    assert contract["workflow"]["id"] == "asset_catalog"
    assert contract["workflow"]["version"] == "1.0.0"
    assert contract["workflow"]["scope"] == "global"
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    assert nodes_by_id["collect_asset_catalog_input"]["outputs"]["required"] == [
        "script", "generate_assets", "background",
    ]
    assert nodes_by_id["collect_asset_catalog_input"]["outputs"]["properties"]["generate_assets"]["enum"] == [
        "手动上传",
        "自动生成",
    ]

    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    assert list(nodes_by_id) == [
        "collect_asset_catalog_input",
        "extract_characters",
        "lookup_existing_assets",
        "match_by_name",
        "semantic_match_characters",
        "enrich_characters",
        "match_variants",
        "check_accessories",
        "review_assets",
        "generate_prompt",
        "generate_image",
        "upload_images",
    ]
    assert {node_id: node["ref"] for node_id, node in nodes_by_id.items()} == {
        "collect_asset_catalog_input": "system.user_input.v1",
        "extract_characters": "ai.deepseek_structured_json.v1",
        "lookup_existing_assets": "tool.asset_lookup.v1",
        "match_by_name": "tool.asset_lookup.v1",
        "semantic_match_characters": "ai.deepseek_structured_json.v1",
        "enrich_characters": "tool.enrich_characters.v1",
        "match_variants": "ai.parallel_deepseek_structured_json.v1",
        "check_accessories": "ai.parallel_deepseek_structured_json.v1",
        "review_assets": "system.human_approval.v1",
        "generate_prompt": "ai.deepseek_structured_json.v1",
        "generate_image": "ai.runninghub_image_to_image.v1",
        "upload_images": "system.human_approval.v1",
    }

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_catalog_workflow_has_conditional_edges(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)

    edges = contract["edges"]
    conditional_edges = [e for e in edges if "when" in e]
    unconditional_edges = [e for e in edges if "when" not in e]

    assert len(conditional_edges) == 2
    assert {
        "from": "review_assets",
        "to": "generate_prompt",
        "when": {"path": "$nodes.collect_asset_catalog_input.output.generate_assets", "equals": "自动生成"},
    } in conditional_edges
    assert {
        "from": "review_assets",
        "to": "upload_images",
        "when": {"path": "$nodes.collect_asset_catalog_input.output.generate_assets", "equals": "手动上传"},
    } in conditional_edges

    assert unconditional_edges == [
        {"from": "START", "to": "collect_asset_catalog_input"},
        {"from": "collect_asset_catalog_input", "to": "extract_characters"},
        {"from": "extract_characters", "to": "lookup_existing_assets"},
        {"from": "lookup_existing_assets", "to": "match_by_name"},
        {"from": "match_by_name", "to": "semantic_match_characters"},
        {"from": "semantic_match_characters", "to": "enrich_characters"},
        {"from": "enrich_characters", "to": "match_variants"},
        {"from": "match_variants", "to": "check_accessories"},
        {"from": "check_accessories", "to": "review_assets"},
        {"from": "generate_prompt", "to": "generate_image"},
        {"from": "generate_image", "to": "END"},
        {"from": "upload_images", "to": "END"},
    ]

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_catalog_extract_characters_output_schema(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    extract_schema = nodes_by_id["extract_characters"]["outputs"]
    assert extract_schema["type"] == "object"
    assert "reasoning" in extract_schema["required"]
    assert "characters" in extract_schema["required"]
    assert "character_names" in extract_schema["required"]

    validate_json_value(
        extract_schema,
        {
            "reasoning": "剧本中叙述段提到林冲在山神庙外踏雪而来，满足收录条件。",
            "characters": [
                {
                    "full_name": "林冲",
                    "aliases": ["林教头"],
                    "summary": "八十万禁军教头，武艺高强。",
                    "character_status": "被发配沧州途中，身着囚服，面带风霜。",
                    "accessories": [],
                }
            ],
            "character_names": ["林冲"],
        },
    )
    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_catalog_semantic_match_output_schema(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    match_schema = nodes_by_id["semantic_match_characters"]["outputs"]
    assert match_schema["type"] == "object"
    assert "match_results" in match_schema["required"]

    validate_json_value(
        match_schema,
        {
            "match_results": [
                {
                    "full_name": "林冲",
                    "matched": False,
                    "reason": "资产库中无匹配角色",
                }
            ]
        },
    )
    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_catalog_match_variants_output_schema(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    variant_schema = nodes_by_id["match_variants"]["outputs"]
    assert variant_schema["type"] == "object"
    assert "results" in variant_schema["required"]

    validate_json_value(
        variant_schema,
        {
            "results": [
                {
                    "full_name": "林冲",
                    "accessories": [],
                    "matched_variant": "",
                    "matched_variant_id": None,
                    "is_new_variant": True,
                    "new_variant_name": "林冲_囚服",
                    "default_variant_status": "八十万禁军教头，身着官服。",
                    "default_variant_storage_uri": "",
                    "reason": "新角色无已有变体",
                }
            ]
        },
    )
    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_catalog_check_accessories_output_schema(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    accessory_schema = nodes_by_id["check_accessories"]["outputs"]
    assert accessory_schema["type"] == "object"
    assert "results" in accessory_schema["required"]

    validate_json_value(
        accessory_schema,
        {
            "results": [
                {
                    "full_name": "林冲",
                    "has_new_accessories": False,
                    "new_accessories": [],
                    "existing_accessories": [],
                    "reason": "无配件",
                }
            ]
        },
    )
    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_catalog_generate_prompt_output_schema(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    prompt_schema = nodes_by_id["generate_prompt"]["outputs"]
    assert prompt_schema["type"] == "object"
    assert "prompt_results" in prompt_schema["required"]

    validate_json_value(
        prompt_schema,
        {
            "prompt_results": [
                {
                    "full_name": "林冲",
                    "think": "角色当前状态为囚服，默认变体为官服，需将官服改为囚服。",
                    "prompt": "请将图中角色的官服改成囚服，保持风格和其它特征不变",
                    "reference_image_url": "https://cdn.test/template-character.png",
                }
            ]
        },
    )
    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_catalog_extract_prompt_includes_key_instructions() -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    system_prompt = nodes_by_id["extract_characters"]["inputs"]["system"]["template"]
    prompt_template = nodes_by_id["extract_characters"]["inputs"]["prompt"]["template"]

    assert "全名" in system_prompt
    assert "世界背景" in system_prompt
    assert "叙述" in system_prompt
    assert "对话" in system_prompt
    assert "思维链" in system_prompt
    assert "reasoning" in system_prompt
    assert "characters" in prompt_template
    assert "full_name" in prompt_template
    assert "character_status" in prompt_template
    assert "accessories" in prompt_template
    assert "character_names" in prompt_template
    assert "reasoning" in prompt_template


def test_asset_catalog_match_by_name_uses_names_array() -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    match_inputs = nodes_by_id["match_by_name"]["inputs"]
    assert match_inputs["names"] == {
        "from": "$nodes.extract_characters.output.character_names",
    }


def test_asset_catalog_generate_image_references_prompt_results() -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    gen_image_inputs = nodes_by_id["generate_image"]["inputs"]
    assert gen_image_inputs["prompt"] == {
        "from": "$nodes.generate_prompt.output.prompt_results.0.prompt",
    }
    assert gen_image_inputs["image_urls"] == {
        "from": "$nodes.generate_prompt.output.prompt_results.0.reference_image_url",
    }


async def test_asset_catalog_auto_generate_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    router = FakeAssetCatalogRouter()
    monkeypatch.setattr(
        "xiagent.workflows.testing.builder.build_node_registry",
        lambda settings: _asset_catalog_registry(router),
    )
    workflow_dir = tmp_path / "empty-workflows"
    workflow_dir.mkdir()
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(workflow_dir)
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    await _seed_file_asset(
        database_path=tmp_path / "workflow-test.sqlite3",
        user_id=session.user.user_id,
        name="塞雷无腿角色模板",
        storage_uri="https://cdn.test/template-character.png",
    )
    answers = iter(["approved"])
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=lambda prompt: next(answers)),
    )

    result = await runner.run_workflow_file(
        ASSET_CATALOG_WORKFLOW_PATH,
        input_data={
            "script": "林冲在山神庙外踏雪而来。",
            "generate_assets": "自动生成",
            "background": "水浒传",
        },
    )

    assert result.task.status == "succeeded"
    executed_node_ids = [execution.node_id for execution in result.node_executions]
    assert "extract_characters" in executed_node_ids
    assert "lookup_existing_assets" in executed_node_ids
    assert "match_by_name" in executed_node_ids
    assert "semantic_match_characters" in executed_node_ids
    assert "enrich_characters" in executed_node_ids
    assert "match_variants" in executed_node_ids
    assert "check_accessories" in executed_node_ids
    assert "review_assets" in executed_node_ids
    assert "generate_prompt" in executed_node_ids
    assert "generate_image" in executed_node_ids
    assert "upload_images" not in executed_node_ids


async def test_asset_catalog_manual_upload_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    router = FakeAssetCatalogRouter()
    monkeypatch.setattr(
        "xiagent.workflows.testing.builder.build_node_registry",
        lambda settings: _asset_catalog_registry(router),
    )
    workflow_dir = tmp_path / "empty-workflows"
    workflow_dir.mkdir()
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(workflow_dir)
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    answers = iter(["approved", "approved"])
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=lambda prompt: next(answers)),
    )

    result = await runner.run_workflow_file(
        ASSET_CATALOG_WORKFLOW_PATH,
        input_data={
            "script": "林冲在山神庙外踏雪而来。",
            "generate_assets": "手动上传",
            "background": "水浒传",
        },
    )

    assert result.task.status == "succeeded"
    executed_node_ids = [execution.node_id for execution in result.node_executions]
    assert "extract_characters" in executed_node_ids
    assert "lookup_existing_assets" in executed_node_ids
    assert "match_by_name" in executed_node_ids
    assert "semantic_match_characters" in executed_node_ids
    assert "enrich_characters" in executed_node_ids
    assert "match_variants" in executed_node_ids
    assert "check_accessories" in executed_node_ids
    assert "review_assets" in executed_node_ids
    assert "upload_images" in executed_node_ids
    assert "generate_prompt" not in executed_node_ids
    assert "generate_image" not in executed_node_ids


class FakeAssetCatalogRouter(ChatModelRouter):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[Any] = []
        self._deepseek_responses = [
            # extract_characters
            (
                '{"reasoning": "剧本中叙述段提到林冲在山神庙外踏雪而来，满足收录条件。", '
                '"characters": [{"full_name": "林冲", "aliases": ["林教头"], '
                '"summary": "八十万禁军教头，武艺高强。", '
                '"character_status": "被发配沧州途中，身着囚服，面带风霜。", '
                '"accessories": []}], '
                '"character_names": ["林冲"]}'
            ),
            # semantic_match_characters
            (
                '{"match_results": [{"full_name": "林冲", "matched": false, '
                '"reason": "资产库中无匹配角色"}]}'
            ),
            # match_variants (parallel - 1 call for 1 character)
            (
                '{"full_name": "林冲", "accessories": [], "matched_variant": "", '
                '"matched_variant_id": null, "is_new_variant": true, '
                '"new_variant_name": "林冲_囚服", '
                '"default_variant_status": "八十万禁军教头，身着官服。", '
                '"default_variant_storage_uri": "", '
                '"reason": "新角色无已有变体"}'
            ),
            # check_accessories (parallel - 1 call for 1 character)
            (
                '{"full_name": "林冲", "has_new_accessories": false, '
                '"new_accessories": [], "existing_accessories": [], '
                '"reason": "无配件"}'
            ),
            # generate_prompt
            (
                '{"prompt_results": [{"full_name": "林冲", '
                '"think": "角色当前状态为囚服，默认变体为官服，需将官服改为囚服。", '
                '"prompt": "请将图中角色的官服改成囚服，保持风格和其它特征不变", '
                '"reference_image_url": "https://cdn.test/template-character.png"}]}'
            ),
        ]

    async def chat(self, request: Any) -> ChatResponse:
        self.requests.append(request)
        if request.provider in ("runninghub_text_to_image", "runninghub_image_to_image"):
            return ChatResponse(
                text="https://cdn.runninghub.test/asset-image.png",
                model=request.model,
                usage={"credits": 1},
                metadata={
                    "provider": request.provider,
                    "results": [{"url": "https://cdn.runninghub.test/asset-image.png"}],
                    "task_id": "asset-task-001",
                    "status": "SUCCESS",
                },
            )
        return ChatResponse(
            text=self._deepseek_responses.pop(0),
            model=request.model,
            usage={"completion_tokens": 1},
            metadata={"provider": request.provider},
        )


def _asset_catalog_registry(router: FakeAssetCatalogRouter) -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(SystemUserInputNode())
    registry.register(HumanApprovalNode())
    registry.register(AssetLookupNode())
    registry.register(CreateTextAssetNode())
    registry.register(EnrichCharactersNode())
    registry.register(
        DeepSeekStructuredJsonNode(
            model_router=router,
            provider="deepseek",
            model="deepseek-test-model",
        )
    )
    registry.register(
        ParallelDeepSeekStructuredJsonNode(
            model_router=router,
            provider="deepseek",
            model="deepseek-test-model",
        )
    )
    registry.register(
        RunningHubImageToImageNode(
            model_router=router,
            provider="runninghub_image_to_image",
            model="runninghub-image-test-model",
        )
    )
    return registry


async def _seed_file_asset(
    *,
    database_path: Path,
    user_id: str,
    name: str,
    storage_uri: str,
) -> None:
    from xiagent.infrastructure.database import connect_db
    from xiagent.core.ids import new_id
    from datetime import UTC, datetime

    asset_id = new_id("asset")
    now = datetime.now(UTC).isoformat()
    async with connect_db(database_path) as db:
        await db.execute(
            """
            INSERT INTO assets (
              asset_id, scope, project_id, asset_type, name, mime_type, content_hash,
              size_bytes, storage_uri, text_content, metadata_json, created_by,
              created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id, "global", None, "file", name, "image/png", None,
                0, storage_uri, None, '{"tags": ["角色"]}', user_id,
                now, now, None,
            ),
        )
        await db.execute(
            """
            INSERT INTO asset_search_fts (asset_id, scope, project_id, search_text)
            VALUES (?, ?, ?, ?)
            """,
            (asset_id, "global", "", name),
        )
