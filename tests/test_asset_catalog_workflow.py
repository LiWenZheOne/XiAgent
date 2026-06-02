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
        "enrich_scenes",
        "match_variants",
        "resolve_character_variant_refs",
        "check_accessories",
        "resolve_accessory_asset_refs",
        "extract_props",
        "lookup_prop_assets",
        "match_props_by_name",
        "enrich_props",
        "review_assets",
        "resolve_approved_assets",
        "filter_assets_for_generation",
        "generate_prompt",
        "upload_images",
        "summarize_episode",
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
        "resolve_character_variant_refs": "tool.resolve_character_variant_refs.v1",
        "check_accessories": "ai.parallel_deepseek_structured_json.v1",
        "resolve_accessory_asset_refs": "tool.resolve_accessory_asset_refs.v1",
        "extract_props": "ai.deepseek_structured_json.v1",
        "lookup_prop_assets": "tool.asset_lookup.v1",
        "match_props_by_name": "tool.asset_lookup.v1",
        "enrich_props": "tool.enrich_characters.v1",
        "review_assets": "system.human_approval.v1",
        "resolve_approved_assets": "ai.deepseek_structured_json.v1",
        "filter_assets_for_generation": "tool.filter_assets_for_generation.v1",
        "generate_prompt": "ai.parallel_deepseek_structured_json.v1",
        "upload_images": "system.human_approval.v1",
        "summarize_episode": "ai.deepseek_structured_json.v1",
        "finish_summary": "tool.episode_metadata_finalize.v1",
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
        {"from": "match_variants", "to": "resolve_character_variant_refs"},
        {"from": "enrich_characters", "to": "check_accessories"},
        {"from": "resolve_character_variant_refs", "to": "resolve_accessory_asset_refs"},
        {"from": "check_accessories", "to": "resolve_accessory_asset_refs"},
        {"from": "resolve_accessory_asset_refs", "to": "review_assets"},
        {"from": "collect_asset_catalog_input", "to": "extract_scenes"},
        {"from": "extract_scenes", "to": "lookup_scene_assets"},
        {"from": "lookup_scene_assets", "to": "match_scenes_by_name"},
        {"from": "match_scenes_by_name", "to": "enrich_scenes"},
        {"from": "enrich_scenes", "to": "review_assets"},
        {"from": "review_assets", "to": "resolve_approved_assets"},
        {"from": "resolve_approved_assets", "to": "filter_assets_for_generation"},
        {"from": "filter_assets_for_generation", "to": "generate_prompt"},
        {"from": "generate_prompt", "to": "upload_images"},
        {"from": "upload_images", "to": "summarize_episode"},
        {"from": "summarize_episode", "to": "finish_summary"},
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
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服"],
                    "aliases": ["林教头"],
                    "summary": "八十万禁军教头，武艺高强。",
                    "character_status": "被发配沧州途中，身着囚服，面带风霜。",
                    "appearance_description": "身着囚服，保留八十万禁军教头的稳定体貌和身份识别特征。",
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
                    "name": "山神庙外",
                    "description": "风雪中的山神庙外有破旧庙门、积雪石阶、香炉陈设和宋代木构屋檐。",
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
                    "asset_type": "prop",
                    "asset_name": "花枪",
                    "description": "宋代花枪以木杆配亮银枪头，红缨装饰，杆身有使用磨痕，便于马上或步战。",
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
                    "target_appearance_description": "黑灰短发，眉眼锋利，短须明显，上身灰色囚衣，保持大圆头、圆鼓身体、短小四肢、简化五官、粗黑描边、平涂色块和圆润卡通比例。",
                    "think": "角色当前状态为囚服，默认变体为官服，需将官服改为囚服。",
                    "prompt": "黑灰短发，眉眼锋利，短须明显，上身灰色囚衣，保持大圆头、圆鼓身体、短小四肢、简化五官、粗黑描边、平涂色块和圆润卡通比例不变",
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
        "appearance_description",
        "description",
        "reference_appearance_description",
    ]
    assert generate_prompt["inputs"]["passthrough_fields"]["value"] == [
        "asset_type",
        "asset_name",
        "asset_tags",
    ]
    assert "reference_image_ref" not in nodes_by_id["generate_prompt"]["outputs"]["properties"]["results"]["items"]["required"]
    assert "视觉资产设定提示词专家" in system_prompt
    assert "图生图使用的修改提示词" in system_prompt
    assert "只写画面可见的外形特征与气质" in system_prompt
    assert "发型、眉毛、胡子、眼睛" in system_prompt
    assert "大圆头、圆鼓身体、无腿，下半身是个类似不倒翁的半球" in system_prompt
    assert "不得改成写实人体、长身比例或其他体型结构" in system_prompt
    assert "不写动作、姿态、表情" in system_prompt
    assert "受伤、疲惫、奔跑、打斗、被绑" in system_prompt
    assert "腿部、脚部、脚踝、鞋、靴、鞋履" in system_prompt
    assert "地点描述空间结构、建筑/地貌、时代质感" in system_prompt
    assert "角色描述不得包含任何材质" in system_prompt
    assert "道具描述形制、材质、颜色、装饰" in system_prompt
    assert "当前资产" in prompt_template
    assert "asset_name 只用于理解目标对象" in prompt_template
    assert "最终外貌描述和 prompt 不得输出人名" in prompt_template
    assert "渔户、村民、公差、兵丁、随从、店小二" in system_prompt
    assert "不得因为信息不足输出“或”“可能”“可选”“任选”“一类”等不确定造型" in system_prompt
    assert "原作对应桥段" in system_prompt
    assert "必须选择一个确定方案" in prompt_template
    assert "不得包含“或”“可能”“可选”“任选”“一类”等不确定表达" in prompt_template
    assert "appearance_description 描述了哪些目标外貌" in prompt_template
    assert "reference_appearance_description 描述了哪些原始外貌" in prompt_template
    assert "目标外貌和参考图外貌之间的差异是什么" in prompt_template
    assert "哪些剧情、动作、状态、腿脚和鞋履信息必须排除" in prompt_template
    assert "空间、建筑/地貌、时代质感、用途和关键视觉元素" in prompt_template
    assert "形制、材质、颜色、装饰、磨损、用途和可见特征" in prompt_template
    assert "target_appearance_description" in prompt_template
    assert "reference_image_ref" not in prompt_template
    assert "不包含固定开头、固定结尾或质量词" in prompt_template
    assert "脸型、面部轮廓、体型、体貌、身材" in prompt_template
    assert "材质、布料质感、纹理或面料工艺" in prompt_template
    assert "最终修改用的提示词" in prompt_template
    assert "明确保持大圆头、圆鼓身体、短小四肢、简化五官、粗黑描边、平涂色块和圆润卡通比例不变" in prompt_template
    assert "不得包含人名、角色名" in prompt_template
    assert "身份、职业、阶层、官职、称号、人物关系、阵营、剧情身份" in prompt_template


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
    assert "character_names" in prompt_template
    assert "reasoning" in prompt_template
    assert "请用提问式思维链步骤完成分析" in system_prompt
    assert "这段剧本中一共出现、在场、发言、行动或被明确提到的角色有哪些" in system_prompt
    assert "候选角色清单" in system_prompt
    assert "当前剧本属于原作的哪个剧情阶段" in system_prompt
    assert "每个角色的长相是什么样的" in system_prompt
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
    assert "按 system 中 12 个问题整理" in prompt_template
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
    assert "材质、造型、颜色、装饰、磨损痕迹、用途和可见特征" in prop_system
    assert "道具设计描述" in prop_prompt


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
    finish_ui = nodes_by_id["finish_summary"]["ui"]
    assert finish_ui["sections"]["output"]["wrapped"] is False
    assert finish_ui["controls"]["output"]["control_id"] == "ui.display.asset_task_summary.v1"
    assert "asset_images" in nodes_by_id["finish_summary"]["outputs"]["properties"]


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
    assert "enrich_scenes" in executed_node_ids
    assert "match_variants" in executed_node_ids
    assert "resolve_character_variant_refs" in executed_node_ids
    assert "check_accessories" in executed_node_ids
    assert "resolve_accessory_asset_refs" in executed_node_ids
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
    assert "enrich_scenes" in executed_node_ids
    assert "match_variants" in executed_node_ids
    assert "resolve_character_variant_refs" in executed_node_ids
    assert "check_accessories" in executed_node_ids
    assert "resolve_accessory_asset_refs" in executed_node_ids
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
                '"characters": [{"asset_type": "character", "asset_name": "林冲", '
                '"asset_tags": ["囚服"], "aliases": ["林教头"], '
                '"summary": "八十万禁军教头，武艺高强。", '
                '"character_status": "被发配沧州途中，身着囚服，面带风霜。", '
                '"appearance_description": "身着囚服，保留八十万禁军教头的稳定体貌和身份识别特征。"'
                '}], '
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
            # resolve_approved_assets
            (
                '{"approved_assets": {"characters": [{"asset_type": "character", "asset_name": "林冲", '
                '"asset_tags": ["囚服"], '
                '"matched": false, "matched_asset_id": null, "matched_asset_name": "", '
                '"aliases": "林教头", "summary": "八十万禁军教头，武艺高强。", '
                '"character_status": "被发配沧州途中，身着囚服，面带风霜。", '
                '"appearance_description": "身着囚服，保留八十万禁军教头的稳定体貌和身份识别特征。", '
                '"reference_appearance_description": "官服参考图，头戴幞头，身穿深色官袍。"}], "assets": [], "props": []}, '
                '"added_assets": [], "reasoning": "无新增资产描述，沿用审核列表。"}'
            ),
            # generate_prompt
            (
                '{"asset_type": "character", "asset_name": "林冲", "asset_tags": ["囚服"], '
                '"target_appearance_description": "黑灰短发，眉眼锋利，短须明显，上身灰色囚衣，保持大圆头、圆鼓身体、短小四肢、简化五官、粗黑描边、平涂色块和圆润卡通比例。", '
                '"think": "角色当前状态为囚服，默认变体为官服，需将官服改为囚服。", '
                '"prompt": "黑灰短发，眉眼锋利，短须明显，上身灰色囚衣，保持大圆头、圆鼓身体、短小四肢、简化五官、粗黑描边、平涂色块和圆润卡通比例不变"}'
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
            return "{}"
        if prompt.endswith("asset_images (JSON): "):
            return "[]"
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
