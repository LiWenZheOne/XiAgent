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
from xiagent.nodes.tools.filter_assets_for_generation import FilterAssetsForGenerationNode
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


def test_asset_catalog_workflow_contract_structure(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)

    assert contract["workflow"]["id"] == "asset_catalog"
    assert contract["workflow"]["version"] == "1.0.0"
    assert contract["workflow"]["scope"] == "global"
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    assert nodes_by_id["collect_asset_catalog_input"]["outputs"]["required"] == [
        "script", "background",
    ]
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
        "enrich_scenes",
        "match_variants",
        "check_accessories",
        "extract_props",
        "lookup_prop_assets",
        "match_props_by_name",
        "enrich_props",
        "review_assets",
        "resolve_approved_assets",
        "filter_assets_for_generation",
        "generate_prompt",
        "upload_images",
        "finish_summary",
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
        "enrich_scenes": "tool.enrich_characters.v1",
        "match_variants": "ai.parallel_deepseek_structured_json.v1",
        "check_accessories": "ai.parallel_deepseek_structured_json.v1",
        "extract_props": "ai.deepseek_structured_json.v1",
        "lookup_prop_assets": "tool.asset_lookup.v1",
        "match_props_by_name": "tool.asset_lookup.v1",
        "enrich_props": "tool.enrich_characters.v1",
        "review_assets": "system.human_approval.v1",
        "resolve_approved_assets": "ai.deepseek_structured_json.v1",
        "filter_assets_for_generation": "tool.filter_assets_for_generation.v1",
        "generate_prompt": "ai.parallel_deepseek_structured_json.v1",
        "upload_images": "system.human_approval.v1",
        "finish_summary": "tool.echo.v1",
    }

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_catalog_workflow_has_conditional_edges(test_settings) -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)

    edges = contract["edges"]
    conditional_edges = [e for e in edges if "when" in e]
    unconditional_edges = [e for e in edges if "when" not in e]

    assert conditional_edges == []

    assert unconditional_edges == [
        {"from": "START", "to": "collect_asset_catalog_input"},
        {"from": "collect_asset_catalog_input", "to": "extract_characters"},
        {"from": "collect_asset_catalog_input", "to": "extract_props"},
        {"from": "extract_characters", "to": "lookup_existing_assets"},
        {"from": "extract_props", "to": "lookup_prop_assets"},
        {"from": "lookup_prop_assets", "to": "match_props_by_name"},
        {"from": "match_props_by_name", "to": "enrich_props"},
        {"from": "enrich_props", "to": "review_assets"},
        {"from": "lookup_existing_assets", "to": "match_by_name"},
        {"from": "match_by_name", "to": "semantic_match_characters"},
        {"from": "semantic_match_characters", "to": "enrich_characters"},
        {"from": "enrich_characters", "to": "match_variants"},
        {"from": "match_variants", "to": "check_accessories"},
        {"from": "check_accessories", "to": "review_assets"},
        {"from": "collect_asset_catalog_input", "to": "extract_scenes"},
        {"from": "extract_scenes", "to": "lookup_scene_assets"},
        {"from": "lookup_scene_assets", "to": "match_scenes_by_name"},
        {"from": "match_scenes_by_name", "to": "enrich_scenes"},
        {"from": "enrich_scenes", "to": "review_assets"},
        {"from": "review_assets", "to": "resolve_approved_assets"},
        {"from": "resolve_approved_assets", "to": "filter_assets_for_generation"},
        {"from": "filter_assets_for_generation", "to": "generate_prompt"},
        {"from": "generate_prompt", "to": "upload_images"},
        {"from": "upload_images", "to": "finish_summary"},
        {"from": "finish_summary", "to": "END"},
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
                    "variant_name": "囚服",
                    "variant_description": "身着囚服，保留八十万禁军教头的稳定体貌和身份识别特征。",
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
                    "name": "山神庙外",
                    "description": "风雪中的山神庙外，林冲踏雪而来。",
                    "time_of_day": "夜晚",
                    "location_type": "户外",
                }
            ],
            "scene_names": ["山神庙外"],
        },
    )

    prop_schema = nodes_by_id["extract_props"]["outputs"]
    validate_json_value(
        prop_schema,
        {
            "reasoning": "剧本叙述段中林冲持有花枪。",
            "props": [
                {
                    "full_name": "花枪",
                    "description": "林冲随身携带的长枪。",
                    "category": "武器",
                }
            ],
            "prop_names": ["花枪"],
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
    validate_json_value(
        variant_schema,
        {
            "results": [
                {
                    "full_name": "何涛",
                    "accessories": [],
                    "matched_variant": "",
                    "matched_variant_id": None,
                    "is_new_variant": True,
                    "new_variant_name": "何涛_公差装束",
                    "default_variant_status": "",
                    "default_variant_storage_uri": "",
                    "default_variant_appearance_description": "",
                    "matched_variant_appearance_description": "",
                    "reason": "资产库无已有变体",
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
    assert "results" in prompt_schema["required"]

    validate_json_value(
        prompt_schema,
        {
            "results": [
                {
                    "full_name": "林冲",
                    "target_appearance_description": "深灰粗布囚服，旧毡笠，面部轮廓清晰。",
                    "think": "角色当前状态为囚服，默认变体为官服，需将官服改为囚服。",
                    "prompt": "深灰粗布囚服，旧毡笠，面部轮廓清晰，保留八十万禁军教头的挺拔体态",
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
    assert "视觉资产设定提示词专家" in system_prompt
    assert "图生图使用的目标描述片段" in system_prompt
    assert "角色资产只生成稳定设定" in system_prompt
    assert "只写画面可见的外貌特征与气质" in system_prompt
    assert "不写身份、职业、阶层、官职、称号、人物关系、阵营、剧情身份" in system_prompt
    assert "不写动作、姿态、表情" in system_prompt
    assert "受伤、疲惫、奔跑、打斗、被绑" in system_prompt
    assert "腿部、脚部、脚踝、鞋、靴、鞋履" in system_prompt
    assert "地点描述空间结构、建筑/地貌、时代质感" in system_prompt
    assert "道具描述形制、材质、颜色、装饰" in system_prompt
    assert "当前资产" in prompt_template
    assert "哪些信息是稳定可见造型" in prompt_template
    assert "哪些身份、剧情、动作、状态、腿脚和鞋履信息必须排除" in prompt_template
    assert "空间、建筑/地貌、时代质感、用途和关键视觉元素" in prompt_template
    assert "形制、材质、颜色、装饰、磨损、用途和可见特征" in prompt_template
    assert "target_appearance_description" in prompt_template
    assert "参考图外貌描述已在资产字段中提供，不要重新生成或改写" in prompt_template
    assert "不包含固定开头、固定结尾或质量词" in prompt_template
    assert "脸型、面部轮廓、五官、体型、体貌、身材" in prompt_template
    assert "只描述资产在画面中可见的外貌特征和气质" in prompt_template
    assert "不得写身份、职业、阶层、官职、称号、人物关系、阵营、剧情身份" in prompt_template


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
    assert "full_name" in prompt_template
    assert "character_status" in prompt_template
    assert "variant_name" in prompt_template
    assert "variant_description" in prompt_template
    assert "accessories" in prompt_template
    assert "character_names" in prompt_template
    assert "reasoning" in prompt_template
    assert "请用提问式思维链步骤完成分析" in system_prompt
    assert "这段剧本中一共出现、在场、发言、行动或被明确提到的角色有哪些" in system_prompt
    assert "候选角色清单" in system_prompt
    assert "当前剧本属于原作的哪个剧情阶段" in system_prompt
    assert "每个角色在当前情景下应该是什么稳定造型" in system_prompt
    assert "这个稳定造型应该叫什么 variant_name" in system_prompt
    assert "被绑起来" in system_prompt
    assert "不是变体依据" in system_prompt
    assert "禁止填\"默认\"、\"基础\"、\"普通\"、\"无特殊造型\"" in system_prompt
    assert "禁止使用\"角色名_服装名\"格式" in system_prompt
    assert "这个变体的稳定视觉设定是什么" in system_prompt
    assert "至少 40 字" in system_prompt
    assert "禁止输出\"默认装束，无特殊造型描述\"" in system_prompt
    assert "按 system 中 12 个问题整理" in prompt_template
    assert "回答\"这个稳定造型应该叫什么？\"" in prompt_template
    assert "禁止输出\"默认\"、\"基础\"、\"普通\"、\"无特殊造型\"" in prompt_template
    assert "回答\"这个变体的稳定视觉设定是什么？\"" in prompt_template
    assert "束缚用绳索" in system_prompt
    assert "summary 只写长期身份" in system_prompt
    assert "character_status 只写此刻" in system_prompt
    assert "不写当前剧情状态" in prompt_template
    assert "不写生平背景" in prompt_template
    scene_system = nodes_by_id["extract_scenes"]["inputs"]["system"]["template"]
    assert "哪些地点需要固化为可复用地点资产" in scene_system
    assert "会多次出现、承载剧情行动、具备明确空间结构/功能" in scene_system
    assert "临时路过、泛泛提及、纯对话中一笔带过" in scene_system
    assert "穿戴类外观元素不作为道具提取" in prop_system
    assert "属于角色变体或角色配件" in prop_system
    assert "普通穿着状态不能作为道具" in prop_system
    assert "不要使用\"服装\"作为道具类别" in prop_prompt


def test_asset_catalog_variant_matching_only_matches_extracted_variants() -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    semantic_system = nodes_by_id["semantic_match_characters"]["inputs"]["system"]["value"]
    semantic_prompt = nodes_by_id["semantic_match_characters"]["inputs"]["prompt"]["template"]
    match_system = nodes_by_id["match_variants"]["inputs"]["system"]["value"]
    match_prompt = nodes_by_id["match_variants"]["inputs"]["prompt_template"]["value"]
    match_schema = nodes_by_id["match_variants"]["outputs"]
    accessory_inputs = nodes_by_id["check_accessories"]["inputs"]
    accessory_system = nodes_by_id["check_accessories"]["inputs"]["system"]["value"]
    accessory_prompt = nodes_by_id["check_accessories"]["inputs"]["prompt_template"]["value"]
    review_prompt = nodes_by_id["review_assets"]["inputs"]["question"]["template"]

    assert "资产库角色匹配器" in semantic_system
    assert "## A. 提取到的角色资产" in semantic_prompt
    assert "## B. 资产库候选角色" in semantic_prompt
    assert "资产库角色变体匹配器" in match_system
    assert "提取到的角色变体资产" in match_system
    assert "变体是否存在已经由上游 extract_characters 决定" in match_system
    assert "variant_name、variant_description、accessories" in match_system
    assert "被绑起来" in match_system
    assert "临时状态必须忽略" in match_system
    assert "## A. 提取到的角色变体资产" in match_prompt
    assert "## B. 资产库候选变体" in match_prompt
    assert "appearance_description" in match_prompt
    assert "default_variant_appearance_description" in match_prompt
    assert "matched_variant_appearance_description" in match_schema["properties"]["results"]["items"]["properties"]
    assert "不得使用被绑、受伤、动作、场景等临时状态命名" in match_prompt
    assert "资产库角色配件匹配器" in accessory_system
    assert "只检查上游已提取配件" in accessory_system
    assert accessory_inputs["items"] == {
        "from": "$nodes.enrich_characters.output.characters",
    }
    assert "## A. 提取到的角色配件" in accessory_prompt
    assert "## B. 资产库候选变体/配件" in accessory_prompt
    assert "不得把被绑" in accessory_system
    assert "### A. 提取到的地点资产" in review_prompt
    assert "### B. 资产库地点名称匹配结果" in review_prompt
    assert "### A. 提取到的道具资产" in review_prompt
    assert "### B. 资产库道具名称匹配结果" in review_prompt


def test_asset_catalog_match_by_name_uses_names_array() -> None:
    contract = load_workflow_file(ASSET_CATALOG_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}

    match_inputs = nodes_by_id["match_by_name"]["inputs"]
    assert match_inputs["names"] == {
        "from": "$nodes.extract_characters.output.character_names",
    }


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
    finish_ui = nodes_by_id["finish_summary"]["ui"]
    assert finish_ui["controls"]["output"]["control_id"] == "ui.display.asset_task_summary.v1"


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
    answers = iter(["", "{}", "approved", "[]", "finish"])
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=lambda prompt: next(answers)),
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
    assert "enrich_scenes" in executed_node_ids
    assert "match_variants" in executed_node_ids
    assert "check_accessories" in executed_node_ids
    assert "extract_props" in executed_node_ids
    assert "lookup_prop_assets" in executed_node_ids
    assert "match_props_by_name" in executed_node_ids
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
    answers = iter(["", "{}", "approved", "[]", "finish"])
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=lambda prompt: next(answers)),
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
    assert "enrich_scenes" in executed_node_ids
    assert "match_variants" in executed_node_ids
    assert "check_accessories" in executed_node_ids
    assert "extract_props" in executed_node_ids
    assert "lookup_prop_assets" in executed_node_ids
    assert "match_props_by_name" in executed_node_ids
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
                '"variant_name": "囚服", '
                '"variant_description": "身着囚服，保留八十万禁军教头的稳定体貌和身份识别特征。", '
                '"accessories": []}], '
                '"character_names": ["林冲"]}'
            ),
            # extract_scenes
            (
                '{"reasoning": "剧本发生在山神庙外。", '
                '"scenes": [{"name": "山神庙外", '
                '"description": "林冲在风雪中的山神庙外踏雪而来。", '
                '"time_of_day": "夜晚", "location_type": "户外"}], '
                '"scene_names": ["山神庙外"]}'
            ),
            # extract_props
            (
                '{"reasoning": "剧本中未出现关键道具。", '
                '"props": [], "prop_names": []}'
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
                '"default_variant_appearance_description": "官服参考图，头戴幞头，身穿深色官袍。", '
                '"matched_variant_appearance_description": "", '
                '"reason": "新角色无已有变体"}'
            ),
            # check_accessories (parallel - 1 call for 1 character)
            (
                '{"full_name": "林冲", "has_new_accessories": false, '
                '"new_accessories": [], "existing_accessories": [], '
                '"reason": "无配件"}'
            ),
            # resolve_approved_assets
            (
                '{"approved_assets": {"characters": [{"type": "character", "name": "林冲", '
                '"matched": false, "matched_asset_id": null, "matched_asset_name": "", '
                '"aliases": "林教头", "summary": "八十万禁军教头，武艺高强。", '
                '"character_status": "被发配沧州途中，身着囚服，面带风霜。", '
                '"variant_name": "囚服", '
                '"variant_description": "身着囚服，保留八十万禁军教头的稳定体貌和身份识别特征。", '
                '"reference_appearance_description": "官服参考图，头戴幞头，身穿深色官袍。", '
                '"accessories": ""}], "assets": [], "props": []}, '
                '"added_assets": [], "reasoning": "无新增资产描述，沿用审核列表。"}'
            ),
            # generate_prompt
            (
                '{"full_name": "林冲", '
                '"target_appearance_description": "深灰粗布囚服，旧毡笠，面部轮廓清晰。", '
                '"think": "角色当前状态为囚服，默认变体为官服，需将官服改为囚服。", '
                '"prompt": "深灰粗布囚服，旧毡笠，面部轮廓清晰，保留八十万禁军教头的挺拔体态", '
                '"reference_image_ref": {"kind": "data_uri", '
                '"data": "data:image/png;base64,dGVtcGxhdGU=", "role": "reference"}}'
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
    registry.register(FilterAssetsForGenerationNode())
    registry.register(CompleteAssetImagesNode())
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
