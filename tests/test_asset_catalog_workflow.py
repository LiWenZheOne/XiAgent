from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite
import pytest

from xiagent.assets.service import SqliteAssetService
from xiagent.core.errors import ValidationError
from xiagent.core.schemas import validate_json_value
from xiagent.infrastructure.migrations import migrate
from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes import build_node_registry
from xiagent.nodes.ai.deepseek_structured_json import DeepSeekStructuredJsonNode
from xiagent.nodes.ai.parallel_deepseek_structured_json import (
    ParallelDeepSeekStructuredJsonNode,
)
from xiagent.nodes.ai.runninghub_image import RunningHubImageToImageNodeV2
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.base import NodeContext
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.system.user_input import SystemUserInputNode
from xiagent.nodes.tools.asset_lookup import AssetLookupNode
from xiagent.nodes.tools.create_text_asset import CreateTextAssetNode
from xiagent.nodes.tools.complete_asset_images import CompleteAssetImagesNode
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.nodes.tools.enrich_characters import EnrichCharactersNode
from xiagent.nodes.tools.episode_metadata import EpisodeMetadataFinalizeNode
from xiagent.nodes.tools.filter_assets_for_generation import FilterAssetsForGenerationNode
from xiagent.nodes.tools.prepare_asset_semantic_match import PrepareAssetSemanticMatchNode
from xiagent.nodes.tools.resolve_accessory_asset_refs import ResolveAccessoryAssetRefsNode
from xiagent.nodes.tools.resolve_character_variant_refs import ResolveCharacterVariantRefsNode
from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.testing import WorkflowTestBuilder
from xiagent.workflows.testing.console import ConsoleIO
from xiagent.workflows.testing.runner import WorkflowTestRunner
from xiagent.workflows.validator import validate_workflow_contract
from xiagent.users.service import SqliteUserService

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


async def test_create_text_asset_uses_context_project(test_settings) -> None:
    node = CreateTextAssetNode()
    descriptor = node.describe()
    assert "project_id" not in descriptor.input_schema["properties"]

    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="asset-node-user", password="secret-123")
    project_a = await users.create_project(owner_user_id=user.user_id, name="project A")
    project_b = await users.create_project(owner_user_id=user.user_id, name="project B")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )
    ctx = NodeContext(
        user_id=user.user_id,
        project_id=project_a.project_id,
        task_id="task_1",
        node_id="create_asset",
        node_execution_id="node_execution_1",
        config={},
        output_schema={},
        asset_service=assets,
        event_sink=None,
        logger=None,
    )

    with pytest.raises(ValidationError) as exc_info:
        await node.run(
            ctx,
            {
                "scope": "project",
                "project_id": project_b.project_id,
                "name": "story seed",
                "text": "content",
            },
        )

    result = await node.run(
        ctx,
        {
            "scope": "project",
            "name": "story seed",
            "text": "content",
        },
    )
    record = await assets.get_asset(
        user_id=user.user_id,
        asset_id=result.output["asset_id"],
        project_id=project_a.project_id,
    )

    assert exc_info.value.code == "create_text_asset_project_mismatch"
    assert record.project_id == project_a.project_id


async def test_asset_lookup_filters_by_structured_identity_tags() -> None:
    class FakeAsset:
        def __init__(self, *, asset_id: str, name: str, tags: list[str]) -> None:
            self.asset_id = asset_id
            self.name = name
            self.asset_type = "file"
            self.mime_type = "image/png"
            self.metadata = {}
            self.text_content = None
            self.storage_uri = None
            self.tags = tags

    class FakeTag:
        def __init__(self, name: str) -> None:
            self.name = name

    class FakeSearchResult:
        def __init__(self, items: list[FakeAsset]) -> None:
            self.items = items
            self.total = len(items)

    class FakeAssetService:
        def __init__(self) -> None:
            self.assets = [
                FakeAsset(
                    asset_id="asset-hetao",
                    name="角色_何涛_官帽、官兵装束、佩刀",
                    tags=["角色", "何涛", "官帽", "官兵装束", "佩刀"],
                ),
                FakeAsset(
                    asset_id="asset-linchong",
                    name="角色_林冲_囚服",
                    tags=["角色", "林冲", "囚服"],
                ),
            ]
            self.search_kwargs: dict[str, Any] | None = None

        async def search_assets(self, **kwargs: Any) -> FakeSearchResult:
            self.search_kwargs = kwargs
            return FakeSearchResult(self.assets)

        async def list_asset_tags(self, **kwargs: Any) -> list[FakeTag]:
            asset = next(item for item in self.assets if item.asset_id == kwargs["asset_id"])
            return [FakeTag(tag) for tag in asset.tags]

    service = FakeAssetService()
    ctx = NodeContext(
        user_id="user-1",
        project_id="project-1",
        task_id="task-1",
        node_id="match_by_identity",
        node_execution_id="exec-identity",
        config={},
        output_schema={},
        asset_service=service,  # type: ignore[arg-type]
        event_sink=None,
        logger=None,
    )

    result = await AssetLookupNode().run(
        ctx,
        {
            "scope": "combined",
            "tags": ["角色"],
            "identity_filters": [
                {"asset_type": "character", "asset_name": "何涛", "asset_tags": ["佩刀", "官兵装束"]},
            ],
            "limit": 200,
        },
    )

    assert service.search_kwargs is not None
    assert service.search_kwargs["keyword"] is None
    assert result.output["total"] == 1
    assert result.output["assets"][0]["asset_id"] == "asset-hetao"


async def test_asset_lookup_identity_does_not_depend_on_tag_order() -> None:
    class FakeAsset:
        def __init__(self, *, asset_id: str, name: str, tags: list[str]) -> None:
            self.asset_id = asset_id
            self.name = name
            self.asset_type = "file"
            self.mime_type = "image/png"
            self.metadata = {}
            self.text_content = None
            self.storage_uri = None
            self.tags = tags

    class FakeTag:
        def __init__(self, name: str) -> None:
            self.name = name

    class FakeSearchResult:
        def __init__(self, items: list[FakeAsset]) -> None:
            self.items = items
            self.total = len(items)

    class FakeAssetService:
        def __init__(self) -> None:
            self.assets = [
                FakeAsset(
                    asset_id="asset-scene-duantougou",
                    name="地点_断头沟_默认",
                    tags=["地点", "默认", "断头沟"],
                ),
                FakeAsset(
                    asset_id="asset-prop-gangcha",
                    name="道具_钢叉_武器_公差",
                    tags=["道具", "钢叉", "武器", "公差"],
                ),
            ]

        async def search_assets(self, **kwargs: Any) -> FakeSearchResult:
            return FakeSearchResult(self.assets)

        async def list_asset_tags(self, **kwargs: Any) -> list[FakeTag]:
            asset = next(item for item in self.assets if item.asset_id == kwargs["asset_id"])
            return [FakeTag(tag) for tag in asset.tags]

    service = FakeAssetService()
    ctx = NodeContext(
        user_id="user-1",
        project_id="project-1",
        task_id="task-1",
        node_id="match_by_identity",
        node_execution_id="exec-identity",
        config={},
        output_schema={},
        asset_service=service,  # type: ignore[arg-type]
        event_sink=None,
        logger=None,
    )

    scene_result = await AssetLookupNode().run(
        ctx,
        {
            "scope": "combined",
            "tags": ["地点"],
            "identity_filters": [
                {"asset_type": "scene", "asset_name": "断头沟", "asset_tags": ["户外", "水道"]},
            ],
            "limit": 200,
        },
    )
    prop_result = await AssetLookupNode().run(
        ctx,
        {
            "scope": "combined",
            "tags": ["道具"],
            "identity_filters": [
                {"asset_type": "prop", "asset_name": "钢叉", "asset_tags": ["武器", "渔具"]},
            ],
            "limit": 200,
        },
    )

    assert [item["asset_id"] for item in scene_result.output["assets"]] == ["asset-scene-duantougou"]
    assert [item["asset_id"] for item in prop_result.output["assets"]] == ["asset-prop-gangcha"]


def test_asset_catalog_workflow_contract_structure(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)

    assert contract["workflow"]["id"] == "asset_catalog"
    assert contract["workflow"]["version"] == "1.0.0"
    assert contract["workflow"]["scope"] == "global"
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    assert nodes_by_id["collect_asset_catalog_input"]["outputs"]["required"] == [
        "script", "episode_name", "background",
    ]
    assert "default" not in nodes_by_id["collect_asset_catalog_input"]["inputs"]["episode_name"]["schema"]
    assert "default" not in nodes_by_id["collect_asset_catalog_input"]["outputs"]["properties"]["episode_name"]
    assert "generate_assets" not in nodes_by_id["collect_asset_catalog_input"]["outputs"]["properties"]

    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    assert list(nodes_by_id) == [
        "collect_asset_catalog_input",
        "extract_characters",
        "lookup_existing_assets",
        "match_by_name",
        "semantic_match_characters",
        "enrich_characters",
        "extract_scenes",
        "lookup_scene_assets",
        "match_scenes_by_name",
        "prepare_scene_semantic_match",
        "semantic_match_scenes",
        "enrich_scenes",
        "match_variants",
        "resolve_character_variant_refs",
        "check_accessories",
        "resolve_accessory_asset_refs",
        "extract_props",
        "lookup_prop_assets",
        "match_props_by_name",
        "prepare_prop_semantic_match",
        "semantic_match_props",
        "enrich_props",
        "review_assets",
        "filter_assets_for_generation",
        "generate_prompt",
        "upload_images",
        "summarize_episode",
        "finish_summary",
        "finish_summary_existing_assets",
    ]
    assert {node_id: node["ref"] for node_id, node in nodes_by_id.items()} == {
        "collect_asset_catalog_input": "system.user_input.v1",
        "extract_characters": "ai.deepseek_structured_json.v1",
        "lookup_existing_assets": "tool.asset_lookup.v1",
        "match_by_name": "tool.asset_lookup.v1",
        "semantic_match_characters": "ai.deepseek_structured_json.v1",
        "enrich_characters": "tool.enrich_characters.v1",
        "extract_scenes": "ai.deepseek_structured_json.v1",
        "lookup_scene_assets": "tool.asset_lookup.v1",
        "match_scenes_by_name": "tool.asset_lookup.v1",
        "prepare_scene_semantic_match": "tool.prepare_asset_semantic_match.v1",
        "semantic_match_scenes": "ai.deepseek_structured_json.v1",
        "enrich_scenes": "tool.enrich_characters.v1",
        "match_variants": "ai.parallel_deepseek_structured_json.v1",
        "resolve_character_variant_refs": "tool.resolve_character_variant_refs.v1",
        "check_accessories": "ai.parallel_deepseek_structured_json.v1",
        "resolve_accessory_asset_refs": "tool.resolve_accessory_asset_refs.v1",
        "extract_props": "ai.deepseek_structured_json.v1",
        "lookup_prop_assets": "tool.asset_lookup.v1",
        "match_props_by_name": "tool.asset_lookup.v1",
        "prepare_prop_semantic_match": "tool.prepare_asset_semantic_match.v1",
        "semantic_match_props": "ai.deepseek_structured_json.v1",
        "enrich_props": "tool.enrich_characters.v1",
        "review_assets": "system.human_approval.v1",
        "filter_assets_for_generation": "tool.filter_assets_for_generation.v1",
        "generate_prompt": "ai.parallel_deepseek_structured_json.v1",
        "upload_images": "system.human_approval.v1",
        "summarize_episode": "ai.deepseek_structured_json.v1",
        "finish_summary": "tool.episode_metadata_finalize.v1",
        "finish_summary_existing_assets": "tool.episode_metadata_finalize.v1",
    }

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_catalog_workflow_has_conditional_edges(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)

    edges = contract["edges"]
    conditional_edges = [e for e in edges if "when" in e]
    unconditional_edges = [e for e in edges if "when" not in e]

    assert conditional_edges == [
        {
            "from": "filter_assets_for_generation",
            "to": "generate_prompt",
            "when": {
                "path": "$nodes.filter_assets_for_generation.output.has_assets_to_generate",
                "equals": True,
            },
        },
        {
            "from": "filter_assets_for_generation",
            "to": "summarize_episode",
            "when": {
                "path": "$nodes.filter_assets_for_generation.output.has_assets_to_generate",
                "equals": False,
            },
        },
        {
            "from": "summarize_episode",
            "to": "finish_summary",
            "when": {
                "path": "$nodes.filter_assets_for_generation.output.has_assets_to_generate",
                "equals": True,
            },
        },
        {
            "from": "summarize_episode",
            "to": "finish_summary_existing_assets",
            "when": {
                "path": "$nodes.filter_assets_for_generation.output.has_assets_to_generate",
                "equals": False,
            },
        },
    ]

    assert unconditional_edges == [
        {"from": "START", "to": "collect_asset_catalog_input"},
        {"from": "collect_asset_catalog_input", "to": "extract_characters"},
        {"from": "collect_asset_catalog_input", "to": "extract_props"},
        {"from": "extract_characters", "to": "lookup_existing_assets"},
        {"from": "extract_props", "to": "lookup_prop_assets"},
        {"from": "lookup_prop_assets", "to": "match_props_by_name"},
        {"from": "match_props_by_name", "to": "prepare_prop_semantic_match"},
        {"from": "prepare_prop_semantic_match", "to": "semantic_match_props"},
        {"from": "semantic_match_props", "to": "enrich_props"},
        {"from": "enrich_props", "to": "review_assets"},
        {"from": "lookup_existing_assets", "to": "match_by_name"},
        {"from": "match_by_name", "to": "semantic_match_characters"},
        {"from": "semantic_match_characters", "to": "enrich_characters"},
        {"from": "enrich_characters", "to": "match_variants"},
        {"from": "match_variants", "to": "resolve_character_variant_refs"},
        {"from": "enrich_characters", "to": "check_accessories"},
        {"from": "resolve_character_variant_refs", "to": "resolve_accessory_asset_refs"},
        {"from": "check_accessories", "to": "resolve_accessory_asset_refs"},
        {"from": "resolve_accessory_asset_refs", "to": "review_assets"},
        {"from": "collect_asset_catalog_input", "to": "extract_scenes"},
        {"from": "extract_scenes", "to": "lookup_scene_assets"},
        {"from": "lookup_scene_assets", "to": "match_scenes_by_name"},
        {"from": "match_scenes_by_name", "to": "prepare_scene_semantic_match"},
        {"from": "prepare_scene_semantic_match", "to": "semantic_match_scenes"},
        {"from": "semantic_match_scenes", "to": "enrich_scenes"},
        {"from": "enrich_scenes", "to": "review_assets"},
        {"from": "review_assets", "to": "filter_assets_for_generation"},
        {"from": "generate_prompt", "to": "upload_images"},
        {"from": "upload_images", "to": "summarize_episode"},
        {"from": "finish_summary", "to": "END"},
        {"from": "finish_summary_existing_assets", "to": "END"},
    ]

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_catalog_extract_characters_output_schema(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    extract_schema = nodes_by_id["extract_characters"]["outputs"]
    assert extract_schema["type"] == "object"
    assert "reasoning" in extract_schema["required"]
    assert "characters" in extract_schema["required"]
    assert "character_names" not in extract_schema["required"]

    validate_json_value(
        extract_schema,
        {
            "reasoning": "剧本中叙述段提到林冲在山神庙外踏雪而来，满足收录条件。",
            "characters": [
                {
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服"],
                    "aliases": ["林教头"],
                    "summary": "八十万禁军教头，武艺高强。",
                    "character_status": "被发配沧州途中，身着囚服，面带风霜。",
                    "appearance_description": "身着囚服，保留八十万禁军教头的稳定体貌和身份识别特征。",
                }
            ],
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
                    "asset_name": "林冲",
                    "matched": False,
                    "reason": "资产库中无匹配角色",
                }
            ]
        },
    )
    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_catalog_scene_and_prop_output_schemas(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    scene_schema = nodes_by_id["extract_scenes"]["outputs"]
    validate_json_value(
        scene_schema,
        {
            "reasoning": "剧本叙述段发生在山神庙外。",
            "scenes": [
                {
                    "asset_type": "scene",
                    "asset_name": "山神庙外",
                    "asset_tags": ["户外", "夜晚"],
                    "description": "风雪中的山神庙外有破旧庙门、积雪石阶、香炉陈设和宋代木构屋檐。",
                    "time_of_day": "夜晚",
                    "location_type": "户外",
                }
            ],
        },
    )

    prop_schema = nodes_by_id["extract_props"]["outputs"]
    validate_json_value(
        prop_schema,
        {
            "reasoning": "剧本叙述段中林冲持有花枪。",
            "props": [
                {
                    "asset_type": "prop",
                    "asset_name": "花枪",
                    "asset_tags": ["武器"],
                    "description": "林冲在山神庙外持用的随身兵器，宋代花枪以木杆配亮银枪头，红缨装饰，杆身有使用磨痕，便于步战。",
                    "category": "武器",
                }
            ],
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
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服"],
                    "matched_asset_id": None,
                    "is_new_variant": True,
                    "reason": "新角色无已有变体",
                }
            ]
        },
    )
    validate_json_value(
        variant_schema,
        {
            "results": [
                {
                    "asset_type": "character",
                    "asset_name": "何涛",
                    "asset_tags": ["公差装束"],
                    "matched_asset_id": None,
                    "is_new_variant": True,
                    "reason": "资产库无已有变体",
                }
            ]
        },
    )

    resolved_schema = nodes_by_id["resolve_character_variant_refs"]["outputs"]
    validate_json_value(
        resolved_schema,
        {
            "results": [
                {
                    "asset_type": "character",
                    "asset_name": "何涛",
                    "asset_tags": ["公差装束"],
                    "matched_asset_id": None,
                    "is_new_variant": True,
                    "default_asset_status": "",
                    "default_asset_storage_uri": "",
                    "default_asset_appearance_description": "",
                    "matched_asset_appearance_description": "",
                    "reason": "资产库无已有变体",
                }
            ]
        },
    )
    scene_match_schema = nodes_by_id["semantic_match_scenes"]["outputs"]
    validate_json_value(
        scene_match_schema,
        {
            "match_results": [
                {
                    "asset_type": "scene",
                    "asset_name": "石碣村湖荡芦苇",
                    "matched": True,
                    "matched_asset_name": "地点_石碣村湖荡芦苇荡",
                    "matched_asset_id": "asset_scene_reeds",
                    "reason": "两者都指石碣村外湖荡芦苇水域。",
                }
            ]
        },
    )
    prop_match_schema = nodes_by_id["semantic_match_props"]["outputs"]
    validate_json_value(
        prop_match_schema,
        {
            "match_results": [
                {
                    "asset_type": "prop",
                    "asset_name": "飞鱼钩",
                    "matched": True,
                    "matched_asset_name": "道具_刀枪飞鱼钩_武器",
                    "matched_asset_id": "asset_prop_hook",
                    "reason": "两者都指同一类飞鱼钩武器。",
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
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服"],
                    "has_new_asset_tags": False,
                    "new_asset_tags": [],
                    "existing_asset_tags": [],
                    "reason": "无配件",
                }
            ]
        },
    )
    resolved_accessory_schema = nodes_by_id["resolve_accessory_asset_refs"]["outputs"]
    validate_json_value(
        resolved_accessory_schema,
        {
            "results": [
                {
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服", "毡笠", "披风"],
                    "has_new_asset_tags": True,
                    "new_asset_tags": ["披风"],
                    "existing_asset_tags": ["毡笠"],
                    "selected_accessory_assets": [
                        {
                            "asset_tag": "毡笠",
                            "matched": True,
                            "asset_id": "asset-hat",
                            "asset_name": "林冲_囚服_毡笠",
                            "asset_ref": {"kind": "asset", "asset_id": "asset-hat", "role": "reference"},
                            "storage_uri": "https://cdn.test/hat.png",
                            "appearance_description": "囚服加毡笠参考图。",
                            "source": "matched_asset_tag",
                        },
                        {
                            "asset_tag": "披风",
                            "matched": False,
                            "asset_id": "asset-base",
                            "asset_name": "林冲_囚服",
                            "asset_ref": {"kind": "asset", "asset_id": "asset-base", "role": "reference"},
                            "storage_uri": "https://cdn.test/base.png",
                            "appearance_description": "囚服基础参考图。",
                            "source": "first_variant_asset",
                        },
                    ],
                    "reason": "毡笠已存在，披风未命中。",
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
    assert "results" in prompt_schema["required"]

    validate_json_value(
        prompt_schema,
        {
            "results": [
                {
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服"],
                    "target_appearance_description": "黑灰短发，眉眼锋利，短须明显，上身灰色囚衣，气质沉稳。",
                    "think": "角色当前状态为囚服，默认变体为官服，需将官服改为囚服。",
                    "prompt": "请将图中角色改成一位黑灰短发、眉眼锋利、短须明显、上身灰色囚衣、气质沉稳的角色",
                    "reference_image_ref": {
                        "kind": "data_uri",
                        "data": "data:image/png;base64,dGVtcGxhdGU=",
                        "role": "reference",
                    },
                }
            ]
        },
    )
    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_catalog_generate_prompt_is_character_design_text() -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    generate_prompt = nodes_by_id["generate_prompt"]
    system_prompt = generate_prompt["inputs"]["system"]["value"]
    prompt_template = generate_prompt["inputs"]["prompt_template"]["value"]

    assert generate_prompt["name"] == "生成资产设定提示词"
    assert generate_prompt["inputs"]["items"] == {
        "from": "$nodes.filter_assets_for_generation.output.approved_assets",
    }
    assert generate_prompt["inputs"]["prompt_fields"]["value"] == [
        "asset_type",
        "asset_name",
        "asset_tags",
        "target_appearance_description",
        "reference_appearance_description",
    ]
    assert generate_prompt["inputs"]["passthrough_fields"]["value"] == [
        "asset_type",
        "asset_name",
        "asset_tags",
        "target_appearance_description",
    ]
    assert "reference_image_ref" not in nodes_by_id["generate_prompt"]["outputs"]["properties"]["results"]["items"]["required"]
    assert "视觉资产设定提示词专家" in system_prompt
    assert "图生图使用的修改提示词" in system_prompt
    assert "只写资产本体的可见目标设定" in system_prompt
    assert "角色优先写圆形脸/圆形头部轮廓、头面外貌、气质、发型/头饰、上身服装层次、颜色搭配、身份识别性上身装饰和必要上身配件" in system_prompt
    assert "角色最终提示词必须明确脸部/头部轮廓保持圆形或圆鼓头" in system_prompt
    assert "在圆形脸基础上设计夸张但简洁的眉眼、极简鼻、图案化胡须等面部识别特征" in system_prompt
    assert "用眉形、眼型和胡须形状表达身份、年龄与性格气质" in system_prompt
    assert "五官保持图案化、圆润、清晰" in system_prompt
    assert "头发和头饰承担身份识别" in system_prompt
    assert "不得写成长脸、方脸、瘦削脸、尖脸或写实面部轮廓" in system_prompt
    assert "风格只作为边界约束，不作为输出内容" in system_prompt
    assert "人名、身份履历、剧情动作、临时状态、表情、镜头、场景气氛" in system_prompt
    assert "角色最终提示词不得描述任何下半身内容，包括腿、脚、鞋履、下装、下肢、四肢长短" in system_prompt
    assert "不得用“球形整体”“无腿”等概括说明下半身" in system_prompt
    assert "这些只作为内部边界，不能写入输出" in system_prompt
    assert "短小四肢" not in prompt_template
    assert "材质、布料质感、纹理或面料工艺" in system_prompt
    assert "地点写空间结构、建筑/地貌、布局、摆设、时代视觉元素" in system_prompt
    assert "道具写物件本体的形制、颜色、装饰、磨损、用途和可见特征" in system_prompt
    assert "必须先按 asset_type 区分 character、scene、prop" in system_prompt
    assert "必须保留“图中的道具”这个对象" in system_prompt
    assert "不得写成“图中的{asset_name}改成”" in system_prompt
    assert "当前资产" in prompt_template
    assert "请用提问式思维链完成判断" in prompt_template
    assert "asset_type 是 character、scene 还是 prop" in prompt_template
    assert "哪些外貌和气质必须替换或补足" in prompt_template
    assert "如何在圆形脸/圆形头部轮廓不变的前提下" in prompt_template
    assert "用夸张但简洁的眉形、眼型、极简鼻、图案化胡须、发型/头饰体现身份、气质和年龄" in prompt_template
    assert "能让角色更具体、更可画" in prompt_template
    assert "最终 prompt 不得出现任何下半身内容，包括腿、脚、鞋履、下装" in prompt_template
    assert "不得写球形下半身等概括说明" in prompt_template
    assert "最合理的一种确定造型是什么" in prompt_template
    assert "如果是地点：这个场景的空间结构、建筑/地貌、布局、摆设、时代视觉元素和用途分别是什么" in prompt_template
    assert "如果是道具：这个物件的主体、形制、颜色、装饰、磨损、用途和可见特征分别是什么" in prompt_template
    assert "最终提示词是否只保留可见目标设定" in prompt_template
    assert "- asset_name" not in prompt_template
    assert "- asset_tags" not in prompt_template
    assert "- target_appearance_description" not in prompt_template
    assert "reference_image_ref" not in prompt_template
    assert "最终修改用的提示词" in prompt_template
    assert "character：以“请将图中角色改成一位……”开头" in prompt_template
    assert "只写稳定人物圆形脸/圆形头部轮廓、图案化眉眼、极简鼻、图案化胡须" in prompt_template
    assert "不输出任何下半身内容" in prompt_template
    assert "不输出画风词、质量词或模型参数" in prompt_template
    assert "scene：以“请将图中场景改成……”开头" in prompt_template
    assert "prop：以“请将图中的道具改成……”开头" in prompt_template
    assert "例如缆绳必须写成“请将图中的道具改成一条缆绳……”" in prompt_template
    assert "不得写成“请将图中的缆绳改成……”" in prompt_template
    assert "不得写成人物、身份、场景或把“船用、绑扎”等标签当成主体" in prompt_template
    assert "以请将图中（角色/场景/道具）改成一位xx性格" not in prompt_template


def test_asset_catalog_extract_prompt_includes_key_instructions() -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    system_prompt = nodes_by_id["extract_characters"]["inputs"]["system"]["template"]
    prompt_template = nodes_by_id["extract_characters"]["inputs"]["prompt"]["template"]
    prop_system = nodes_by_id["extract_props"]["inputs"]["system"]["template"]
    prop_prompt = nodes_by_id["extract_props"]["inputs"]["prompt"]["template"]

    assert "全名" in system_prompt
    assert "世界背景" in system_prompt
    assert "叙述" in system_prompt
    assert "对话" in system_prompt
    assert "思维链" in system_prompt
    assert "reasoning" in system_prompt
    assert "characters" in prompt_template
    assert "asset_name" in prompt_template
    assert "character_status" in prompt_template
    assert "appearance_description" in prompt_template
    assert "character_names" not in prompt_template
    assert "reasoning" in prompt_template
    assert "请用提问式思维链步骤完成分析" in system_prompt
    assert "这段剧本中一共出现、在场、发言、行动或被明确提到的角色有哪些" in system_prompt
    assert "候选角色清单" in system_prompt
    assert "当前剧本属于原作的哪个剧情阶段" in system_prompt
    assert "接收禀报、回应、下令、增派、调拨、任命、带队、押送、审问、指挥" in system_prompt
    assert "官职称谓、身份称谓或多人合称只要在当前场景中真实发言、被禀报、做出决定或执行命令" in system_prompt
    assert "最终防漏检查" in system_prompt
    assert "被禀报者、下令者、调度者、执行者" in system_prompt
    assert "每个角色的长相是什么样的" in system_prompt
    assert "角色脸部/头部轮廓必须保持圆形或圆鼓头" in system_prompt
    assert "只在圆形脸的基础上设计夸张但简洁的眉眼、极简鼻、胡须和发型/头饰" in system_prompt
    assert "眉形、眼型和胡须形状要用于表达身份、年龄和性格气质" in system_prompt
    assert "五官应图案化、圆润、清晰" in system_prompt
    assert "圆形脸/圆形头部轮廓" in prompt_template
    assert "在当前情景下应该是什么造型" in system_prompt
    assert "这个稳定造型应该叫什么标签" in system_prompt
    assert "被绑起来" in system_prompt
    assert "不是资产标签依据" in system_prompt
    assert "禁止用被绑、受伤、押送、奔跑等临时状态命名" in system_prompt
    assert "不得包含服装、配件或类型前缀" in prompt_template
    assert "这个角色的稳定视觉设定是什么" in system_prompt
    assert "至少 40 字" in system_prompt
    assert "不要描述任何材质、布料质感、纹理或面料工艺" in system_prompt
    assert "不得包含服装、配件或类型前缀" in prompt_template
    assert "按 system 中 13 个问题整理" in prompt_template
    assert "asset_tags" in prompt_template
    assert "不得包含服装、配件或类型前缀" in prompt_template
    assert "回答\"这个角色的稳定视觉设定是什么？\"" in prompt_template
    assert "束缚用绳索" in system_prompt
    assert "summary 只写长期身份" in system_prompt
    assert "character_status 只写此刻" in system_prompt
    assert "不写当前剧情状态" in prompt_template
    assert "不写生平背景" in prompt_template
    scene_system = nodes_by_id["extract_scenes"]["inputs"]["system"]["template"]
    assert "哪些地点需要固化为可复用地点资产" in scene_system
    assert "会多次出现、承载剧情行动、具备明确空间结构/功能" in scene_system
    assert "临时路过、泛泛提及、纯对话中一笔带过" in scene_system
    assert "场景物件、陈设、布局和装饰风格" in scene_system
    assert "穿戴类外观元素不作为道具提取" in prop_system
    assert "属于角色变体或角色配件" in prop_system
    assert "普通穿着状态、交通载具、建筑空间不能作为道具" in prop_system
    assert "船、舟、渔船、官船、楼船、马车、轿子" in prop_system
    assert "大型载具、建筑、场所或可供角色进入/停留的空间，不作为道具提取" in prop_system
    assert "船桨、缆绳、船篙" in prop_system
    assert "不要使用\"服装\"、\"载具\"、\"建筑\"、\"场景\"作为道具类别" in prop_prompt
    assert "必须同时包含两类信息" in prop_system
    assert "外观/造型" in prop_system
    assert "整体形制、尺寸比例、材质、颜色、装饰、磨损痕迹、用途和可见特征" in prop_system
    assert "整体形制、尺寸比例" in prop_prompt
    assert "不得只写来历" in prop_prompt
    assert "道具设计描述" in prop_prompt
    assert "来历/来源" in prop_system
    assert "从哪里出现、由谁持有/使用/争夺" in prop_prompt


def test_asset_catalog_variant_matching_only_matches_extracted_variants() -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    semantic_system = nodes_by_id["semantic_match_characters"]["inputs"]["system"]["value"]
    semantic_prompt = nodes_by_id["semantic_match_characters"]["inputs"]["prompt"]["template"]
    match_system = nodes_by_id["match_variants"]["inputs"]["system"]["value"]
    match_prompt = nodes_by_id["match_variants"]["inputs"]["prompt_template"]["value"]
    match_schema = nodes_by_id["match_variants"]["outputs"]
    accessory_inputs = nodes_by_id["check_accessories"]["inputs"]
    accessory_ref_inputs = nodes_by_id["resolve_accessory_asset_refs"]["inputs"]
    accessory_system = nodes_by_id["check_accessories"]["inputs"]["system"]["value"]
    accessory_prompt = nodes_by_id["check_accessories"]["inputs"]["prompt_template"]["value"]
    review_prompt = nodes_by_id["review_assets"]["inputs"]["question"]["template"]

    assert "资产库角色匹配器" in semantic_system
    assert "## A. 提取到的角色资产" in semantic_prompt
    assert "## B. 资产库候选角色" in semantic_prompt
    assert "资产库角色变体匹配器" in match_system
    assert "提取到的角色变体资产" in match_system
    assert "变体是否存在已经由上游 extract_characters 决定" in match_system
    assert "asset_name、asset_tags、appearance_description" in match_system
    assert "被绑起来" in match_system
    assert "临时状态必须忽略" in match_system
    assert "## A. 提取到的角色变体资产" in match_prompt
    assert "## B. 资产库候选变体" in match_prompt
    assert "appearance_description" in match_prompt
    assert "default_variant_appearance_description" not in match_prompt
    assert "default_variant_status" not in match_schema["properties"]["results"]["items"]["properties"]
    assert "matched_variant_appearance_description" not in match_schema["properties"]["results"]["items"]["properties"]
    assert nodes_by_id["resolve_character_variant_refs"]["inputs"]["variant_results"] == {
        "from": "$nodes.match_variants.output.results",
    }
    assert "matched_asset_appearance_description" in nodes_by_id["resolve_character_variant_refs"]["outputs"]["properties"]["results"]["items"]["properties"]
    assert "资产库角色配件匹配器" in accessory_system
    assert "只检查上游已提取配件" in accessory_system
    assert accessory_inputs["items"] == {
        "from": "$nodes.enrich_characters.output.characters",
    }
    assert accessory_ref_inputs["variant_results"] == {
        "from": "$nodes.resolve_character_variant_refs.output.results",
    }
    assert accessory_ref_inputs["accessory_results"] == {
        "from": "$nodes.check_accessories.output.results",
    }
    assert "selected_accessory_assets" in nodes_by_id["resolve_accessory_asset_refs"]["outputs"]["properties"]["results"]["items"]["properties"]
    assert "## A. 提取到的角色配件" in accessory_prompt
    assert "## B. 资产库候选变体/配件" in accessory_prompt
    assert "不得把被绑" in accessory_system
    assert "资产库地点匹配器" in nodes_by_id["semantic_match_scenes"]["inputs"]["system"]["value"]
    assert "资产库道具匹配器" in nodes_by_id["semantic_match_props"]["inputs"]["system"]["value"]
    assert "只能使用 asset_name、asset_tags、description" in nodes_by_id["semantic_match_scenes"]["inputs"]["prompt"]["template"]
    assert "只能使用 asset_name、asset_tags、description" in nodes_by_id["semantic_match_props"]["inputs"]["prompt"]["template"]
    assert nodes_by_id["semantic_match_scenes"]["inputs"]["prompt"]["vars"]["scenes"] == {
        "from": "$nodes.prepare_scene_semantic_match.output.items",
    }
    assert nodes_by_id["semantic_match_scenes"]["inputs"]["prompt"]["vars"]["existing_assets"] == {
        "from": "$nodes.prepare_scene_semantic_match.output.candidates",
    }
    assert nodes_by_id["semantic_match_props"]["inputs"]["prompt"]["vars"]["props"] == {
        "from": "$nodes.prepare_prop_semantic_match.output.items",
    }
    assert nodes_by_id["semantic_match_props"]["inputs"]["prompt"]["vars"]["existing_assets"] == {
        "from": "$nodes.prepare_prop_semantic_match.output.candidates",
    }
    assert "### A. 提取到的地点资产" in review_prompt
    assert "### B. 资产库地点身份匹配结果" in review_prompt
    assert "### C. 资产库地点语义匹配结果" in review_prompt
    assert "### A. 提取到的道具资产" in review_prompt
    assert "### B. 资产库道具身份匹配结果" in review_prompt
    assert "### C. 资产库道具语义匹配结果" in review_prompt


def test_asset_catalog_match_nodes_use_identity_filters() -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    match_inputs = nodes_by_id["match_by_name"]["inputs"]
    assert "names" not in match_inputs
    assert match_inputs["identity_filters"] == {
        "from": "$nodes.extract_characters.output.characters",
    }
    assert nodes_by_id["match_scenes_by_name"]["inputs"]["identity_filters"] == {
        "from": "$nodes.extract_scenes.output.scenes",
    }
    assert nodes_by_id["enrich_scenes"]["inputs"]["semantic_matches"] == {
        "from": "$nodes.semantic_match_scenes.output.match_results",
    }
    assert nodes_by_id["prepare_scene_semantic_match"]["inputs"]["items"] == {
        "from": "$nodes.extract_scenes.output.scenes",
    }
    assert nodes_by_id["prepare_scene_semantic_match"]["inputs"]["candidates"] == {
        "from": "$nodes.lookup_scene_assets.output.assets",
    }
    assert nodes_by_id["match_props_by_name"]["inputs"]["identity_filters"] == {
        "from": "$nodes.extract_props.output.props",
    }
    assert nodes_by_id["enrich_props"]["inputs"]["semantic_matches"] == {
        "from": "$nodes.semantic_match_props.output.match_results",
    }
    assert nodes_by_id["prepare_prop_semantic_match"]["inputs"]["items"] == {
        "from": "$nodes.extract_props.output.props",
    }
    assert nodes_by_id["prepare_prop_semantic_match"]["inputs"]["candidates"] == {
        "from": "$nodes.lookup_prop_assets.output.assets",
    }


def test_asset_catalog_lookup_matches_all_asset_types_by_tags() -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    for node_id in [
        "lookup_existing_assets",
        "match_by_name",
        "lookup_scene_assets",
        "match_scenes_by_name",
        "lookup_prop_assets",
        "match_props_by_name",
    ]:
        assert "asset_type" not in nodes_by_id[node_id]["inputs"]


def test_asset_catalog_image_completion_references_prompt_results() -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    upload_inputs = nodes_by_id["upload_images"]["inputs"]
    assert upload_inputs["prompt_results"] == {
        "from": "$nodes.generate_prompt.output.results",
    }
    assert upload_inputs["enriched_characters"] == {
        "from": "$nodes.enrich_characters.output.characters",
    }
    upload_ui = nodes_by_id["upload_images"]["ui"]
    assert upload_ui["controls"]["interaction"]["control_id"] == "ui.interaction.asset_image_cards.v1"
    assert upload_ui["controls"]["interaction"]["options"]["default_reference_templates"] == {
        "character": "塞雷2d角色模板",
        "scene": "塞雷2d地点模板",
        "prop": "塞雷2d道具模板",
    }
    assert upload_ui["sections"]["input"]["visible"] is False
    assert upload_ui["sections"]["output"]["visible"] is False
    assert upload_ui["sections"]["events"]["visible"] is False

    assert "prepare_asset_images" not in nodes_by_id
    assert "generate_missing_asset_images" not in nodes_by_id
    finish_inputs = nodes_by_id["finish_summary"]["inputs"]
    assert finish_inputs["asset_images"] == {
        "from": "$nodes.upload_images.output.asset_images",
    }
    assert finish_inputs["prompt_results"] == {
        "from": "$nodes.upload_images.output.prompt_results",
    }
    assert finish_inputs["generation_summary"] == {
        "from": "$nodes.filter_assets_for_generation.output.generation_summary",
    }
    finish_existing_inputs = nodes_by_id["finish_summary_existing_assets"]["inputs"]
    assert finish_existing_inputs["asset_images"] == {"value": []}
    assert finish_existing_inputs["prompt_results"] == {"value": []}
    assert finish_existing_inputs["generation_summary"] == {
        "from": "$nodes.filter_assets_for_generation.output.generation_summary",
    }
    finish_ui = nodes_by_id["finish_summary"]["ui"]
    assert finish_ui["sections"]["output"]["wrapped"] is False
    assert finish_ui["controls"]["output"]["control_id"] == "ui.display.asset_task_summary.v1"
    assert "asset_images" in nodes_by_id["finish_summary"]["outputs"]["properties"]
    assert "generation_summary" in nodes_by_id["finish_summary"]["outputs"]["properties"]
    assert "generation_summary" in nodes_by_id["finish_summary_existing_assets"]["outputs"]["properties"]


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
        name="塞雷2d角色模板",
        storage_uri="https://cdn.test/template-character.png",
    )
    answer = _asset_catalog_test_answer()
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=answer),
    )

    result = await runner.run_workflow_file(
        ASSET_CATALOG_WORKFLOW_PATH,
        input_data={
            "script": "林冲在山神庙外踏雪而来。",
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
    assert "extract_scenes" in executed_node_ids
    assert "lookup_scene_assets" in executed_node_ids
    assert "match_scenes_by_name" in executed_node_ids
    assert "prepare_scene_semantic_match" in executed_node_ids
    assert "semantic_match_scenes" in executed_node_ids
    assert "enrich_scenes" in executed_node_ids
    assert "match_variants" in executed_node_ids
    assert "resolve_character_variant_refs" in executed_node_ids
    assert "check_accessories" in executed_node_ids
    assert "resolve_accessory_asset_refs" in executed_node_ids
    assert "extract_props" in executed_node_ids
    assert "lookup_prop_assets" in executed_node_ids
    assert "match_props_by_name" in executed_node_ids
    assert "prepare_prop_semantic_match" in executed_node_ids
    assert "semantic_match_props" in executed_node_ids
    assert "enrich_props" in executed_node_ids
    assert "review_assets" in executed_node_ids
    assert "filter_assets_for_generation" in executed_node_ids
    assert "generate_prompt" in executed_node_ids
    assert "upload_images" in executed_node_ids
    assert "finish_summary" in executed_node_ids
    assert "prepare_asset_images" not in executed_node_ids
    assert "generate_missing_asset_images" not in executed_node_ids
    assert "merge_completed_asset_images" not in executed_node_ids
    assert "merge_uploaded_asset_images" not in executed_node_ids


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
    await _seed_file_asset(
        database_path=tmp_path / "workflow-test.sqlite3",
        user_id=session.user.user_id,
        name="塞雷2d角色模板",
        storage_uri="https://cdn.test/template-character.png",
    )
    answer = _asset_catalog_test_answer()
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=answer),
    )

    result = await runner.run_workflow_file(
        ASSET_CATALOG_WORKFLOW_PATH,
        input_data={
            "script": "林冲在山神庙外踏雪而来。",
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
    assert "extract_scenes" in executed_node_ids
    assert "lookup_scene_assets" in executed_node_ids
    assert "match_scenes_by_name" in executed_node_ids
    assert "prepare_scene_semantic_match" in executed_node_ids
    assert "semantic_match_scenes" in executed_node_ids
    assert "enrich_scenes" in executed_node_ids
    assert "match_variants" in executed_node_ids
    assert "resolve_character_variant_refs" in executed_node_ids
    assert "check_accessories" in executed_node_ids
    assert "resolve_accessory_asset_refs" in executed_node_ids
    assert "extract_props" in executed_node_ids
    assert "lookup_prop_assets" in executed_node_ids
    assert "match_props_by_name" in executed_node_ids
    assert "prepare_prop_semantic_match" in executed_node_ids
    assert "semantic_match_props" in executed_node_ids
    assert "enrich_props" in executed_node_ids
    assert "review_assets" in executed_node_ids
    assert "filter_assets_for_generation" in executed_node_ids
    assert "generate_prompt" in executed_node_ids
    assert "upload_images" in executed_node_ids
    assert "finish_summary" in executed_node_ids
    assert "prepare_asset_images" not in executed_node_ids
    assert "generate_missing_asset_images" not in executed_node_ids
    assert "merge_uploaded_asset_images" not in executed_node_ids
    assert "merge_completed_asset_images" not in executed_node_ids


async def test_asset_catalog_skips_prompt_generation_when_all_assets_matched(
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
    answer = _asset_catalog_all_matched_answer()
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=answer),
    )

    result = await runner.run_workflow_file(
        ASSET_CATALOG_WORKFLOW_PATH,
        input_data={
            "script": "林冲在山神庙外踏雪而来。",
            "background": "水浒传",
        },
    )

    assert result.task.status == "succeeded"
    executed_node_ids = [execution.node_id for execution in result.node_executions]
    assert "filter_assets_for_generation" in executed_node_ids
    assert "generate_prompt" not in executed_node_ids
    assert "upload_images" not in executed_node_ids
    assert "summarize_episode" in executed_node_ids
    assert "finish_summary" not in executed_node_ids
    assert "finish_summary_existing_assets" in executed_node_ids
    finish_execution = next(
        execution for execution in result.node_executions
        if execution.node_id == "finish_summary_existing_assets"
    )
    assert finish_execution.output_snapshot["generation_summary"] == {
        "total_asset_count": 2,
        "new_asset_count": 0,
        "matched_asset_count": 2,
        "has_assets_to_generate": False,
    }


class FakeAssetCatalogRouter(ChatModelRouter):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[Any] = []
        self._deepseek_responses = [
            # extract_characters
            (
                '{"reasoning": "剧本中叙述段提到林冲在山神庙外踏雪而来，满足收录条件。", '
                '"characters": [{"asset_type": "character", "asset_name": "林冲", '
                '"asset_tags": ["囚服"], "aliases": ["林教头"], '
                '"summary": "八十万禁军教头，武艺高强。", '
                '"character_status": "被发配沧州途中，身着囚服，面带风霜。", '
                '"appearance_description": "身着囚服，保留八十万禁军教头的稳定体貌和身份识别特征。"'
                '}]}'
            ),
            # extract_scenes
            (
                '{"reasoning": "剧本发生在山神庙外。", '
                '"scenes": [{"asset_type": "scene", "asset_name": "山神庙外", "asset_tags": ["户外", "夜晚"], '
                '"description": "林冲在风雪中的山神庙外踏雪而来。", '
                '"time_of_day": "夜晚", "location_type": "户外"}]}'
            ),
            # extract_props
            (
                '{"reasoning": "剧本中未出现关键道具。", '
                '"props": []}'
            ),
            # semantic_match_characters
            (
                '{"match_results": [{"asset_name": "林冲", "matched": false, '
                '"reason": "资产库中无匹配角色"}]}'
            ),
            # match_variants (parallel - 1 call for 1 character)
            (
                '{"asset_type": "character", "asset_name": "林冲", "asset_tags": ["囚服"], '
                '"matched_asset_id": null, "matched_asset_ref": null, "is_new_variant": true, '
                '"reason": "新角色无已有变体"}'
            ),
            # check_accessories (parallel - 1 call for 1 character)
            (
                '{"asset_type": "character", "asset_name": "林冲", "asset_tags": ["囚服"], '
                '"has_new_asset_tags": false, "new_asset_tags": [], "existing_asset_tags": [], '
                '"reason": "无配件"}'
            ),
            # generate_prompt
            (
                '{"asset_type": "character", "asset_name": "林冲", "asset_tags": ["囚服"], '
                '"target_appearance_description": "黑灰短发，眉眼锋利，短须明显，上身灰色囚衣，气质沉稳。", '
                '"think": "角色当前状态为囚服，默认变体为官服，需将官服改为囚服。", '
                '"prompt": "请将图中角色改成一位黑灰短发、眉眼锋利、短须明显、上身灰色囚衣、气质沉稳的角色"}'
            ),
            # summarize_episode
            (
                '{"episode_summary": "本集围绕林冲行至山神庙外的情节展开，表现其发配途中的孤冷处境，'
                '并为后续山神庙相关事件和角色资产使用提供稳定剧情背景。"}'
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
        request_text = "\n".join(
            message.content if isinstance(message.content, str) else str(message.content)
            for message in request.messages
        )
        if "请从以下剧本中提取所有角色资产信息" in request_text:
            text = (
                '{"reasoning": "剧本中叙述段提到林冲在山神庙外踏雪而来，满足收录条件。", '
                '"characters": [{"asset_type": "character", "asset_name": "林冲", '
                '"asset_tags": ["囚服"], "aliases": ["林教头"], '
                '"summary": "八十万禁军教头，武艺高强。", '
                '"character_status": "被发配沧州途中，身着囚服，面带风霜。", '
                '"appearance_description": "身着囚服，保留八十万禁军教头的稳定体貌和身份识别特征。"'
                '}]}'
            )
        elif "请从以下剧本中提取所有地点资产信息" in request_text:
            text = (
                '{"reasoning": "剧本发生在山神庙外。", '
                '"scenes": [{"asset_type": "scene", "asset_name": "山神庙外", "asset_tags": ["户外", "夜晚"], '
                '"description": "林冲在风雪中的山神庙外踏雪而来。", '
                '"time_of_day": "夜晚", "location_type": "户外"}]}'
            )
        elif "请从以下剧本中提取所有道具资产信息" in request_text:
            text = '{"reasoning": "剧本中未出现关键道具。", "props": []}'
        elif "请判断以下未匹配角色是否与资产库中已有角色是同一人" in request_text:
            text = (
                '{"match_results": [{"asset_name": "林冲", "matched": false, '
                '"reason": "资产库中无匹配角色"}]}'
            )
        elif "请判断以下地点资产是否与资产库中已有地点是同一空间/场所" in request_text:
            text = (
                '{"match_results": [{"asset_type": "scene", "asset_name": "山神庙外", "matched": false, '
                '"matched_asset_name": "", "matched_asset_id": "", "reason": "资产库中无匹配地点"}]}'
            )
        elif "请判断以下道具资产是否与资产库中已有道具是同一可复用物件" in request_text:
            text = '{"match_results": []}'
        elif "资产库角色变体匹配器" in request_text:
            text = (
                '{"asset_type": "character", "asset_name": "林冲", "asset_tags": ["囚服"], '
                '"matched_asset_id": null, "matched_asset_ref": null, "is_new_variant": true, '
                '"reason": "新角色无已有变体"}'
            )
        elif "资产库角色配件匹配器" in request_text:
            text = (
                '{"asset_type": "character", "asset_name": "林冲", "asset_tags": ["囚服"], '
                '"has_new_asset_tags": false, "new_asset_tags": [], "existing_asset_tags": [], '
                '"reason": "无配件"}'
            )
        elif "视觉资产设定提示词专家" in request_text:
            text = (
                '{"asset_type": "character", "asset_name": "林冲", "asset_tags": ["囚服"], '
                '"target_appearance_description": "黑灰短发，眉眼锋利，短须明显，上身灰色囚衣，气质沉稳。", '
                '"think": "角色当前状态为囚服，默认变体为官服，需将官服改为囚服。", '
                '"prompt": "请将图中角色改成一位黑灰短发、眉眼锋利、短须明显、上身灰色囚衣、气质沉稳的角色"}'
            )
        elif "请为以下剧本生成集剧情概括" in request_text:
            text = (
                '{"episode_summary": "本集围绕林冲行至山神庙外的情节展开，表现其发配途中的孤冷处境，'
                '并为后续山神庙相关事件和角色资产使用提供稳定剧情背景。"}'
            )
        else:
            text = self._deepseek_responses.pop(0)
        return ChatResponse(
            text=text,
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
    registry.register(PrepareAssetSemanticMatchNode())
    registry.register(ResolveCharacterVariantRefsNode())
    registry.register(ResolveAccessoryAssetRefsNode())
    registry.register(FilterAssetsForGenerationNode())
    registry.register(CompleteAssetImagesNode())
    registry.register(EpisodeMetadataFinalizeNode())
    registry.register(EchoToolNode())
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
        RunningHubImageToImageNodeV2(
            model_router=router,
            provider="runninghub_image_to_image",
            model="runninghub-image-test-model",
        )
    )
    return registry


def _asset_catalog_test_answer():
    decisions = iter(["approved", "finish"])

    def answer(prompt: str) -> str:
        if prompt.endswith("script: "):
            return "林冲在山神庙外踏雪而来。"
        if prompt.endswith("episode_name: "):
            return "测试集"
        if prompt.endswith("background: "):
            return "水浒传"
        if prompt.endswith("approved_assets (JSON): "):
            return (
                '{"characters": [{"asset_type": "character", "asset_name": "林冲", '
                '"asset_tags": ["囚服"], '
                '"matched": false, "matched_asset_id": null, "matched_asset_name": "", '
                '"aliases": ["林教头"], "summary": "八十万禁军教头，武艺高强。", '
                '"character_status": "被发配沧州途中，身着囚服，面带风霜。", '
                '"appearance_description": "身着囚服，保留八十万禁军教头的稳定体貌和身份识别特征。", '
                '"reference_appearance_description": "官服参考图，头戴幞头，身穿深色官袍。"}], '
                '"assets": [{"asset_type": "scene", "asset_name": "山神庙外", '
                '"asset_tags": ["户外", "夜晚"], "matched": false, '
                '"matched_asset_id": null, "matched_asset_name": "", '
                '"description": "林冲在风雪中的山神庙外踏雪而来。", '
                '"location_type": "户外", "time_of_day": "夜晚"}], '
                '"props": []}'
            )
        if prompt.endswith("asset_images (JSON): "):
            return "[]"
        if prompt.endswith("additional_asset_request: "):
            return ""
        if prompt.endswith("decision: "):
            return next(decisions)
        raise AssertionError(f"Unexpected console prompt: {prompt}")

    return answer


def _asset_catalog_all_matched_answer():
    decisions = iter(["approved"])

    def answer(prompt: str) -> str:
        if prompt.endswith("script: "):
            return "林冲在山神庙外踏雪而来。"
        if prompt.endswith("episode_name: "):
            return "测试集"
        if prompt.endswith("background: "):
            return "水浒传"
        if prompt.endswith("approved_assets (JSON): "):
            return (
                '{"characters": [{"asset_type": "character", "asset_name": "林冲", '
                '"asset_tags": ["囚服"], '
                '"matched": true, "matched_asset_id": "asset-linchong-prisoner", '
                '"matched_asset_name": "林冲"}], '
                '"assets": [{"asset_type": "scene", "asset_name": "山神庙外", '
                '"asset_tags": ["户外", "夜晚"], "matched": true, '
                '"matched_asset_id": "asset-temple-outside", '
                '"matched_asset_name": "山神庙外", '
                '"description": "林冲在风雪中的山神庙外踏雪而来。"}], '
                '"props": []}'
            )
        if prompt.endswith("additional_asset_request: "):
            return ""
        if prompt.endswith("decision: "):
            return next(decisions)
        raise AssertionError(f"Unexpected console prompt: {prompt}")

    return answer


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
    tag_id = new_id("asset_tag")
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
                0, storage_uri, None,
                '{"appearance_description": "官服参考图，头戴幞头，身穿深色官袍。"}',
                user_id,
                now, now, None,
            ),
        )
        await db.execute(
            """
            INSERT INTO asset_tags (
              tag_id, scope, project_id, name, description, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tag_id, "global", None, "角色", None, user_id, now, now),
        )
        await db.execute(
            """
            INSERT INTO asset_index_entries (
              entry_id, scope, project_id, asset_id, collection_id, tag_id,
              search_text, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (new_id("asset_index"), "global", None, asset_id, None, tag_id, name, now, now),
        )
        await db.execute(
            """
            INSERT INTO asset_search_fts (asset_id, scope, project_id, search_text)
            VALUES (?, ?, ?, ?)
            """,
            (asset_id, "global", "", name),
        )
