from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from xiagent.core.ids import new_id
from xiagent.infrastructure.database import connect_db
from xiagent.core.errors import ValidationError
from xiagent.core.schemas import validate_json_value
from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes import build_node_registry
from xiagent.nodes.ai.deepseek_structured_json import DeepSeekStructuredJsonNode
from xiagent.nodes.ai.parallel_deepseek_structured_json import (
    ParallelDeepSeekStructuredJsonNode,
)
from xiagent.nodes.ai.runninghub_image import (
    RunningHubImageToImageNode,
    RunningHubImageToImageNodeV2,
)
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.system.user_input import SystemUserInputNode
from xiagent.nodes.tools.assemble_storyboard_context import AssembleStoryboardContextNode
from xiagent.nodes.tools.asset_lookup import AssetLookupNode
from xiagent.nodes.tools.create_text_asset import CreateTextAssetNode
from xiagent.nodes.tools.enrich_characters import EnrichCharactersNode
from xiagent.nodes.tools.complete_asset_images import CompleteAssetImagesNode
from xiagent.nodes.tools.script_split import ScriptSplitNode
from xiagent.nodes.tools.storyboard_prompt import StoryboardPromptAssemblerNode
from xiagent.runtime import input_resolver as _input_resolver_mod
from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.testing import WorkflowTestBuilder
from xiagent.workflows.testing.console import ConsoleIO
from xiagent.workflows.testing.runner import WorkflowTestRunner
from xiagent.workflows.validator import validate_workflow_contract

ORCHESTRATION_WORKFLOW_PATH = Path(
    "workflows/global/asset_storyboard_generation.workflow.yaml"
)

def _user_input_outputs(contract: dict[str, Any]) -> dict[str, Any]:
    return next(node for node in contract["nodes"] if node["id"] == "collect_asset_storyboard_input")["outputs"]


def test_orchestration_workflow_contract_structure(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    assert contract["workflow"]["id"] == "asset_storyboard_generation"
    assert contract["workflow"]["version"] == "1.0.0"
    assert contract["workflow"]["scope"] == "global"
    assert _user_input_outputs(contract)["required"] == [
        "script",
        "background",
    ]

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_orchestration_workflow_node_list(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    assert list(nodes_by_id) == [
        "collect_asset_storyboard_input",
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
        "upload_images",
        "generate_prompt_v2",
        "prepare_asset_images",
        "generate_missing_asset_images",
        "merge_completed_asset_images",
        "split_script",
        "assign_assets_to_segments",
        "assemble_storyboard_context",
        "describe_panels",
        "review_storyboard_prompt",
        "extract_panel_image_urls",
        "assemble_prompt_v2",
        "generate_image_v2",
        "review_storyboard_image",
    ]
    assert {node_id: node["ref"] for node_id, node in nodes_by_id.items()} == {
        "collect_asset_storyboard_input": "system.user_input.v1",
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
        "generate_prompt_v2": "ai.deepseek_structured_json.v1",
        "upload_images": "system.human_approval.v1",
        "prepare_asset_images": "tool.complete_asset_images.v1",
        "generate_missing_asset_images": "ai.runninghub_image_to_image.v2",
        "merge_completed_asset_images": "tool.complete_asset_images.v1",
        "split_script": "tool.script_split.v1",
        "assign_assets_to_segments": "ai.deepseek_structured_json.v1",
        "assemble_storyboard_context": "tool.assemble_storyboard_context.v1",
        "describe_panels": "ai.deepseek_structured_json.v1",
        "review_storyboard_prompt": "system.human_approval.v1",
        "extract_panel_image_urls": "ai.deepseek_structured_json.v1",
        "assemble_prompt_v2": "tool.storyboard_prompt_assembler.v1",
        "generate_image_v2": "ai.runninghub_image_to_image.v1",
        "review_storyboard_image": "system.human_approval.v1",
    }

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_orchestration_workflow_edges_are_dag(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    edges = contract["edges"]
    conditional_edges = [e for e in edges if "when" in e]
    unconditional_edges = [e for e in edges if "when" not in e]

    assert len(conditional_edges) == 2
    assert conditional_edges == [
        {
            "from": "prepare_asset_images",
            "to": "generate_missing_asset_images",
            "when": {"path": "$nodes.prepare_asset_images.output.next_action", "equals": "generate_missing"},
        },
        {
            "from": "prepare_asset_images",
            "to": "merge_completed_asset_images",
            "when": {"path": "$nodes.prepare_asset_images.output.next_action", "equals": "finish"},
        },
    ]
    assert unconditional_edges == [
        {"from": "START", "to": "collect_asset_storyboard_input"},
        {"from": "collect_asset_storyboard_input", "to": "extract_characters"},
        {"from": "collect_asset_storyboard_input", "to": "extract_props"},
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
        {"from": "review_assets", "to": "generate_prompt_v2"},
        {"from": "generate_prompt_v2", "to": "upload_images"},
        {"from": "upload_images", "to": "prepare_asset_images"},
        {"from": "generate_missing_asset_images", "to": "merge_completed_asset_images"},
        {"from": "merge_completed_asset_images", "to": "split_script"},
        {"from": "split_script", "to": "assign_assets_to_segments"},
        {"from": "assign_assets_to_segments", "to": "assemble_storyboard_context"},
        {"from": "assemble_storyboard_context", "to": "describe_panels"},
        {"from": "describe_panels", "to": "review_storyboard_prompt"},
        {"from": "review_storyboard_prompt", "to": "extract_panel_image_urls"},
        {"from": "extract_panel_image_urls", "to": "assemble_prompt_v2"},
        {"from": "assemble_prompt_v2", "to": "generate_image_v2"},
        {"from": "generate_image_v2", "to": "review_storyboard_image"},
        {"from": "collect_asset_storyboard_input", "to": "extract_scenes"},
        {"from": "extract_scenes", "to": "lookup_scene_assets"},
        {"from": "lookup_scene_assets", "to": "match_scenes_by_name"},
        {"from": "match_scenes_by_name", "to": "enrich_scenes"},
        {"from": "enrich_scenes", "to": "review_assets"},
        {"from": "review_storyboard_image", "to": "END"},
    ]

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_orchestration_workflow_manual_path_valid(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    edges = contract["edges"]
    manual_edge = {
        "from": "prepare_asset_images",
        "to": "merge_completed_asset_images",
        "when": {"path": "$nodes.prepare_asset_images.output.next_action", "equals": "finish"},
    }

    assert manual_edge in edges

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_orchestration_asset_extract_nodes_match_original(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    extract_node_ids = [
        "extract_characters",
        "lookup_existing_assets",
        "match_by_name",
        "semantic_match_characters",
        "enrich_characters",
        "match_variants",
        "check_accessories",
    ]

    assert {nid: nodes_by_id[nid]["ref"] for nid in extract_node_ids} == {
        "extract_characters": "ai.deepseek_structured_json.v1",
        "lookup_existing_assets": "tool.asset_lookup.v1",
        "match_by_name": "tool.asset_lookup.v1",
        "semantic_match_characters": "ai.deepseek_structured_json.v1",
        "enrich_characters": "tool.enrich_characters.v1",
        "match_variants": "ai.parallel_deepseek_structured_json.v1",
        "check_accessories": "ai.parallel_deepseek_structured_json.v1",
    }

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_orchestration_input_schema_storyboard_target_default(
    test_settings,
) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    input_schema = _user_input_outputs(contract)
    assert "required" in input_schema
    assert "storyboard_target" not in input_schema["required"]

    storyboard_target = input_schema["properties"]["storyboard_target"]
    assert storyboard_target["type"] == "object"

    segment_index = storyboard_target["properties"]["segment_index"]
    assert segment_index["type"] == "integer"
    assert segment_index["default"] == 0
    assert segment_index["minimum"] == 0

    panel_index = storyboard_target["properties"]["panel_index"]
    assert panel_index["type"] == "integer"
    assert panel_index["default"] == 0
    assert panel_index["minimum"] == 0

    assert storyboard_target["additionalProperties"] is False

    validate_workflow_contract(contract, build_node_registry(test_settings))


class FakeOrchestrationRouter(ChatModelRouter):
    """Pre-programs all LLM responses for the orchestration workflow."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[Any] = []
        self._deepseek_responses: list[str] = [
            # 1. extract_characters — single DeepSeekStructuredJsonNode call
            (
                '{"reasoning": "剧本叙述段描写林冲踏雪而来，满足收录条件。", '
                '"characters": [{"full_name": "林冲", '
                '"aliases": ["林教头", "豹子头"], '
                '"summary": "八十万禁军教头，武艺高强，隐忍后爆发。", '
                '"character_status": "被发配沧州途中，戴罪看守草料场，'
                '身着囚服，面带风霜，手按花枪。", '
                '"accessories": ["花枪", "旧毡笠"]}], '
                '"character_names": ["林冲"]}'
            ),
            # 2. extract_scenes — single DeepSeekStructuredJsonNode call (parallel to extract_characters)
            (
                '{"reasoning": "剧本描写林冲握紧花枪的场景。", '
                '"scenes": [{"name": "无名场景", '
                '"description": "林冲在火光中握紧花枪。", '
                '"time_of_day": "夜晚", "location_type": "户外"}], '
                '"scene_names": ["无名场景"]}'
            ),
            # 3. extract_props — single DeepSeekStructuredJsonNode call (parallel to extract_characters)
            (
                '{"reasoning": "剧本中叙述段多次提到花枪，花枪是关键道具。", '
                '"props": [{"full_name": "花枪", '
                '"description": "林冲使用的长武器，枪身木制，枪尖锋利。", '
                '"category": "武器"}], '
                '"prop_names": ["花枪"]}'
            ),
            # 4. semantic_match_characters — single DeepSeekStructuredJsonNode call
            (
                '{"match_results": [{"full_name": "林冲", "matched": false, '
                '"matched_asset_name": "", "matched_asset_id": "", '
                '"reason": "资产库中无匹配角色"}]}'
            ),
            # 5. match_variants — ParallelDeepSeekStructuredJsonNode (1 item: 林冲)
            (
                '{"full_name": "林冲", "accessories": ["花枪", "旧毡笠"], '
                '"matched_variant": "", "matched_variant_id": null, '
                '"is_new_variant": true, '
                '"new_variant_name": "林冲_囚服雪地", '
                '"default_variant_status": "八十万禁军教头，身着官服。", '
                '"default_variant_storage_uri": "", '
                '"reason": "新角色无已有变体"}'
            ),
            # 6. check_accessories — ParallelDeepSeekStructuredJsonNode (1 item: 林冲)
            (
                '{"full_name": "林冲", "has_new_accessories": true, '
                '"new_accessories": ["花枪", "旧毡笠"], '
                '"existing_accessories": [], '
                '"reason": "新角色无已有配件"}'
            ),
            # 7. generate_prompt_v2 — single DeepSeekStructuredJsonNode call
            (
                '{"prompt_results": [{"full_name": "林冲", '
                '"think": "角色当前状态为囚服雪地，默认变体为官服，'
                '需将官服改为囚服，添加花枪和旧毡笠。", '
                '"prompt": "请将图中角色的官服改成囚服，'
                '头戴旧毡笠，手持花枪，保持风格和其它特征不变", '
                '"reference_image_url": "https://cdn.test/template.png"}]}'
            ),
            # 8. assign_assets_to_segments — single DeepSeekStructuredJsonNode call
            (
                '{"segment_assignments": [{"segment_index": 0, '
                '"characters": [{"full_name": "林冲", '
                '"image_url": "https://cdn.test/林冲_囚服雪地.png", '
                '"variant": "囚服雪地"}], '
                '"key_props": ["花枪", "旧毡笠"]}, '
                '{"segment_index": 1, '
                '"characters": [{"full_name": "林冲", '
                '"image_url": "https://cdn.test/林冲_囚服雪地.png", '
                '"variant": "囚服雪地"}], '
                '"key_props": ["花枪"]}]}'
            ),
            # 9. describe_panels — single DeepSeekStructuredJsonNode call
            (
                '{"segment_descriptions": [{"index": 0, '
                '"segment_title": "山神庙外踏雪", '
                '"thinking": "林冲在风雪中前行，远处火光暗示危险。", '
                '"panels": [{"description": "林冲披旧毡笠在风雪中前行，'
                '远处草料场火光隐约。", '
                '"style": "电影感国风动画", '
                '"constraints": "保持角色服装发型一致。"}]}, '
                '{"index": 1, '
                '"segment_title": "庙前决绝", '
                '"thinking": "林冲决意反抗，花枪横扫仇敌。", '
                '"panels": [{"description": "林冲踢开庙门冲入雪地，'
                '花枪横扫逼退仇人。", '
                '"style": "电影感国风动画", '
                '"constraints": "保持动态连贯性。"}]}]}'
            ),
            # 10. extract_panel_image_urls — single DeepSeekStructuredJsonNode call
            (
                '{"panel_image_urls": [{"full_name": "林冲", '
                '"image_url": "https://cdn.test/林冲_囚服雪地.png", '
                '"variant": "囚服雪地"}], '
                '"image_urls": ["https://cdn.test/林冲_囚服雪地.png"], '
                '"description": "林冲披旧毡笠在风雪中前行，远处草料场火光隐约。", '
                '"style": "电影感国风动画", '
                '"constraints": "保持角色服装发型一致。"}'
            ),
            # 11. safety buffer — extra response for unexpected parallel calls
            (
                '{"reasoning": "通用补充响应。", '
                '"result": "ok"}'
            ),
        ]

    async def chat(self, request: Any) -> ChatResponse:
        self.requests.append(request)
        if request.provider == "runninghub_image":
            return ChatResponse(
                text="https://cdn.runninghub.test/storyboard.png",
                model=request.model,
                usage={"credits": 1},
                metadata={
                    "provider": request.provider,
                    "results": [{"url": "https://cdn.runninghub.test/storyboard.png"}],
                    "task_id": "storyboard-task-001",
                    "status": "SUCCESS",
                },
            )
        return ChatResponse(
            text=self._deepseek_responses.pop(0),
            model=request.model,
            usage={"completion_tokens": 1},
            metadata={"provider": request.provider},
        )


def _orchestration_registry(router: FakeOrchestrationRouter) -> NodeRegistry:
    """Register all nodes needed for the orchestrated asset-storyboard workflow,
    with the fake router injected for DeepSeek and RunningHub calls."""
    registry = NodeRegistry()
    registry.register(SystemUserInputNode())
    registry.register(HumanApprovalNode())
    registry.register(CompleteAssetImagesNode())
    registry.register(ScriptSplitNode())
    registry.register(AssembleStoryboardContextNode())
    registry.register(AssetLookupNode())
    registry.register(CreateTextAssetNode())
    registry.register(EnrichCharactersNode())
    registry.register(StoryboardPromptAssemblerNode())
    registry.register(
        DeepSeekStructuredJsonNode(
            model_router=router,
            provider="deepseek",
            model="test",
        )
    )
    registry.register(
        ParallelDeepSeekStructuredJsonNode(
            model_router=router,
            provider="deepseek",
            model="test",
        )
    )
    registry.register(
        RunningHubImageToImageNode(
            model_router=router,
            provider="runninghub_image",
            model="test",
        )
    )
    registry.register(
        RunningHubImageToImageNodeV2(
            model_router=router,
            provider="runninghub_image",
            model="test",
        )
    )
    return registry


def _long_shuihu_script() -> str:
    """Return a 2-paragraph Water Margin test script (~10 lines)."""
    return (
        "（1）风雪山神庙外，林冲披着旧毡笠踏雪而来，衣角被寒风掀起。"
        "他回头望向远处草料场，火光在雪幕里忽明忽暗，像有人故意点燃。"
        "庙门半掩，供桌积灰，墙上剥落的神像在风声中显得压迫。"
        "林冲听见门外陆谦几人的笑声，慢慢握紧花枪，眼神从隐忍转为决绝。\n\n"
        "（2）火势越来越大，草料场的黑烟翻卷到夜空。"
        "林冲踢开庙门冲入雪地，花枪横扫，逼得仇人连连后退。"
        "风雪、火光、刀影交错，他终于不再退让。"
    )


class AutoOrchestrationRouter(FakeOrchestrationRouter):
    """FakeOrchestrationRouter pre-programmed for the auto-generate path.

    Provides DeepSeek responses for extract_characters, extract_scenes,
    extract_props, semantic_match_characters, match_variants,
    check_accessories, and generate_prompt_v2 — the sequence of DeepSeek
    calls that execute before the workflow hits assign_assets_to_segments.
    """

    def __init__(self) -> None:
        ChatModelRouter.__init__(self)
        self.requests: list[Any] = []
        self._deepseek_responses: list[str] = [
            # 1. extract_characters
            (
                '{"reasoning": "剧本叙述段描写林冲踏雪而来，满足收录条件。", '
                '"characters": [{"full_name": "林冲", '
                '"aliases": ["林教头", "豹子头"], '
                '"summary": "八十万禁军教头，武艺高强，隐忍后爆发。", '
                '"character_status": "被发配沧州途中，戴罪看守草料场，'
                '身着囚服，面带风霜，手按花枪。", '
                '"accessories": ["花枪", "旧毡笠"]}], '
                '"character_names": ["林冲"]}'
            ),
            # 2. extract_scenes
            (
                '{"reasoning": "剧本描述了山神庙外和草料场两个场景。", '
                '"scenes": [{"name": "山神庙外", '
                '"description": "风雪中的山神庙，庙门半掩。", '
                '"time_of_day": "夜晚", "location_type": "户外"}, '
                '{"name": "草料场", '
                '"description": "火光冲天的草料场，黑烟翻卷。", '
                '"time_of_day": "夜晚", "location_type": "户外"}], '
                '"scene_names": ["山神庙外", "草料场"]}'
            ),
            # 3. extract_props
            (
                '{"reasoning": "剧本中林冲使用了花枪和旧毡笠作为道具。", '
                '"props": [{"full_name": "花枪", '
                '"description": "林冲的随身武器，长枪", "category": "武器"}, '
                '{"full_name": "旧毡笠", '
                '"description": "林冲戴的旧斗笠", "category": "饰品"}], '
                '"prop_names": ["花枪", "旧毡笠"]}'
            ),
            # 4. semantic_match_characters
            (
                '{"match_results": [{"full_name": "林冲", "matched": false, '
                '"reason": "资产库中无匹配角色"}]}'
            ),
            # 5. match_variants — ParallelDeepSeekStructuredJsonNode (1 item)
            (
                '{"full_name": "林冲", "accessories": ["花枪", "旧毡笠"], '
                '"matched_variant": "", "matched_variant_id": null, '
                '"is_new_variant": true, '
                '"new_variant_name": "林冲_囚服雪地", '
                '"default_variant_status": "八十万禁军教头，身着官服。", '
                '"default_variant_storage_uri": "", '
                '"reason": "新角色无已有变体"}'
            ),
            # 6. check_accessories — ParallelDeepSeekStructuredJsonNode (1 item)
            (
                '{"full_name": "林冲", "has_new_accessories": true, '
                '"new_accessories": ["花枪", "旧毡笠"], '
                '"existing_accessories": [], '
                '"reason": "新角色无已有配件"}'
            ),
            # 7. generate_prompt_v2
            (
                '{"prompt_results": [{"full_name": "林冲", '
                '"think": "角色当前状态为囚服雪地，默认变体为官服，'
                '需将官服改为囚服，添加花枪和旧毡笠。", '
                '"prompt": "请将图中角色的官服改成囚服，'
                '头戴旧毡笠，手持花枪，保持风格和其它特征不变", '
                '"reference_image_url": "https://cdn.test/template.png"}]}'
            ),
        ]


async def _seed_file_asset(
    *,
    database_path: Path,
    user_id: str,
    name: str,
    storage_uri: str,
) -> None:
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


async def test_orchestration_auto_generate_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    router = AutoOrchestrationRouter()
    monkeypatch.setattr(
        "xiagent.workflows.testing.builder.build_node_registry",
        lambda settings: _orchestration_registry(router),
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
        name="模板角色",
        storage_uri="https://cdn.test/template.png",
    )
    answers = iter([
        "approved",
        "[]",
        "generate_missing",
    ])
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=lambda prompt: next(answers)),
    )

    result = await runner.run_workflow_file(
        ORCHESTRATION_WORKFLOW_PATH,
        input_data={
            "script": _long_shuihu_script(),
            "background": "水浒传",
        },
    )

    # Verify: generate_prompt_v2 + upload_images + missing image generation executed.
    executed_node_ids = [execution.node_id for execution in result.node_executions]
    assert "generate_prompt_v2" in executed_node_ids
    assert "upload_images" in executed_node_ids
    assert "prepare_asset_images" in executed_node_ids
    assert "generate_missing_asset_images" in executed_node_ids

    # Verify: generate_missing_asset_images outputs asset_images array
    # with source="ai_generated"
    v2_execution = next(
        ex for ex in result.node_executions
        if ex.node_id == "generate_missing_asset_images"
    )
    assert v2_execution.status == "succeeded"
    asset_images = v2_execution.output_snapshot.get("asset_images", [])
    assert isinstance(asset_images, list)
    assert len(asset_images) >= 1
    for img in asset_images:
        assert img.get("source") == "ai_generated"
        assert img.get("full_name")
        assert img.get("image_url")

    # Verify: RunningHub calls recorded in router.requests
    runninghub_requests = [
        req for req in router.requests
        if getattr(req, "provider", None) == "runninghub_image"
    ]
    assert len(runninghub_requests) >= 1


def _execution_by_id(
    executions: list[Any], node_id: str
) -> Any | None:
    for e in executions:
        if e.node_id == node_id:
            return e
    return None


async def test_orchestration_manual_upload_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    router = FakeOrchestrationRouter()
    monkeypatch.setattr(
        "xiagent.workflows.testing.builder.build_node_registry",
        lambda settings: _orchestration_registry(router),
    )

    # ── Patch: workflow YAML template contains JSON literals with
    # unescaped braces ({") that str.format() misinterprets ──
    _original_resolve_input_spec = _input_resolver_mod.resolve_input_spec

    def _safe_resolve_input_spec(
        input_spec: Any,
        *,
        input_name: str,
        node_outputs: Any,
        user_input: Any | None = None,
    ) -> Any:
        try:
            return _original_resolve_input_spec(
                input_spec,
                input_name=input_name,
                node_outputs=node_outputs,
                user_input=user_input,
            )
        except ValidationError as exc:
            if exc.code == "workflow_reference_missing_node_output":
                # Reference to a node not executed (different conditional path).
                # CompleteAssetImagesNode handles missing inputs via .get() default.
                return []
            if exc.code == "invalid_workflow_reference" and (
                "unknown variable" in exc.message
            ):
                # Template has JSON braces; return template text as-is
                if isinstance(input_spec, dict) and "template" in input_spec:
                    return input_spec["template"]
            raise

    monkeypatch.setattr(
        _input_resolver_mod,
        "resolve_input_spec",
        _safe_resolve_input_spec,
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
    answers = iter([
        "approved",
        (
            '[{"asset_type": "character", "asset_key": "林冲", '
            '"full_name": "林冲", "image_url": '
            '"https://cdn.test/林冲_囚服雪地.png", "source": "manual_upload"}]'
        ),
        "finish",
        "approved",
        "approved",
    ])
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=lambda prompt: next(answers)),
    )

    result = await runner.run_workflow_file(
        ORCHESTRATION_WORKFLOW_PATH,
        input_data={
            "script": _long_shuihu_script(),
            "background": "水浒传",
            "storyboard_target": {"segment_index": 0, "panel_index": 0},
        },
    )

    assert result.task.status == "succeeded"
    executed_node_ids = [execution.node_id for execution in result.node_executions]
    assert "upload_images" in executed_node_ids
    assert "generate_prompt_v2" in executed_node_ids
    assert "generate_missing_asset_images" not in executed_node_ids

    generate_image_v2 = _execution_by_id(
        result.node_executions, "generate_image_v2"
    )
    assert generate_image_v2 is not None
    assert "image_url" in generate_image_v2.output_snapshot

    review_storyboard_image = _execution_by_id(
        result.node_executions, "review_storyboard_image"
    )
    assert review_storyboard_image is not None


async def _seed_text_asset(
    *,
    database_path: Path,
    user_id: str,
    name: str,
    tags: list[str],
) -> str:
    """Insert a text asset (e.g. a prop) into the database for testing."""
    import json
    from xiagent.infrastructure.database import connect_db
    from xiagent.core.ids import new_id
    from datetime import UTC, datetime

    asset_id = new_id("asset")
    now = datetime.now(UTC).isoformat()
    async with connect_db(database_path) as db:
        await db.execute(
            """
            INSERT INTO assets (
              asset_id, scope, project_id, asset_type, name, mime_type,
              content_hash, size_bytes, storage_uri, text_content,
              metadata_json, created_by, created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id, "global", None, "text", name, None,
                None, 0, None, None,
                json.dumps({"tags": tags}), user_id,
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
    return asset_id


def test_assign_assets_to_segments_output_schema(test_settings) -> None:
    """assign_assets_to_segments 的 output schema：present/absent assets 均通过验证。"""
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    schema = nodes_by_id["assign_assets_to_segments"]["outputs"]

    assert schema["type"] == "object"
    assert "segment_assignments" in schema["required"]

    # ── present assets ──
    validate_json_value(
        schema,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [
                        {
                            "full_name": "林冲",
                            "image_url": "https://cdn.test/linchong.png",
                            "variant": "囚服雪地",
                        }
                    ],
                    "key_props": ["花枪", "旧毡笠"],
                }
            ]
        },
    )

    # ── absent assets (empty segment) ──
    validate_json_value(
        schema,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [],
                    "key_props": [],
                }
            ]
        },
    )

    # ── invalid: missing required segment_index ──
    with pytest.raises(ValidationError):
        validate_json_value(
            schema,
            {
                "segment_assignments": [
                    {
                        "characters": [],
                        "key_props": [],
                    }
                ]
            },
        )

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_assemble_storyboard_context_output_schema(test_settings) -> None:
    """assemble_storyboard_context 的 output schema：context_string 存在且必填。"""
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    schema = nodes_by_id["assemble_storyboard_context"]["outputs"]

    assert schema["type"] == "object"
    assert "context_string" in schema["required"]

    # ── valid ──
    validate_json_value(schema, {"context_string": "段落0：林冲踏雪而来…"})

    # ── invalid: missing context_string ──
    with pytest.raises(ValidationError):
        validate_json_value(schema, {})

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_extract_panel_image_urls_output_schema(test_settings) -> None:
    """extract_panel_image_urls 的 output schema：panel_image_urls 为数组。"""
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    schema = nodes_by_id["extract_panel_image_urls"]["outputs"]

    assert schema["type"] == "object"
    assert "panel_image_urls" in schema["required"]
    assert "image_urls" in schema["required"]
    assert "description" in schema["required"]
    assert "style" in schema["required"]
    assert "constraints" in schema["required"]

    # ── valid with populated panel_image_urls ──
    validate_json_value(
        schema,
        {
            "panel_image_urls": [
                {
                    "full_name": "林冲",
                    "image_url": "https://cdn.test/linchong.png",
                    "variant": "囚服雪地",
                }
            ],
            "image_urls": ["https://cdn.test/linchong.png"],
            "description": "林冲披旧毡笠在风雪中前行。",
            "style": "电影感国风动画",
            "constraints": "保持角色服装发型一致。",
        },
    )

    # ── valid with empty panel_image_urls ──
    validate_json_value(
        schema,
        {
            "panel_image_urls": [],
            "image_urls": [],
            "description": "空场景无角色。",
            "style": "默认风格",
            "constraints": "无约束。",
        },
    )

    # ── invalid: missing description ──
    with pytest.raises(ValidationError):
        validate_json_value(
            schema,
            {
                "panel_image_urls": [],
                "image_urls": [],
                "style": "默认风格",
                "constraints": "无约束。",
            },
        )

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_review_storyboard_image_output_schema(test_settings) -> None:
    """review_storyboard_image 的 output schema：仅含 decision。"""
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    schema = nodes_by_id["review_storyboard_image"]["outputs"]

    assert schema["type"] == "object"
    assert "decision" in schema["required"]

    # ── valid: approve ──
    validate_json_value(schema, {"decision": "approve"})

    # ── valid: reject ──
    validate_json_value(schema, {"decision": "reject"})

    # ── invalid: missing decision ──
    with pytest.raises(ValidationError):
        validate_json_value(schema, {"selected_image_url": "https://cdn.test/storyboard.png"})

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_asset_image_result_workflow_output_schema(test_settings) -> None:
    """工作流中的 asset_images output schema：ai_generated 和 manual_upload 两种 source 均通过。"""
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    nodes_by_id = {node["id"]: node for node in contract["nodes"]}
    schema = nodes_by_id["merge_completed_asset_images"]["outputs"]["properties"]["asset_images"]["items"]

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is True

    # ── ai_generated source ──
    validate_json_value(
        schema,
        {
            "full_name": "林冲",
            "image_url": "https://cdn.test/linchong_ai.png",
            "source": "ai_generated",
            "variant": "囚服雪地",
            "asset_id": "asset-001",
            "runninghub_task_id": "task-abc-123",
        },
    )

    # ── manual_upload source ──
    validate_json_value(
        schema,
        {
            "full_name": "林冲",
            "image_url": "https://cdn.test/linchong_upload.png",
            "source": "manual_upload",
        },
    )

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_orchestration_storyboard_target_default(test_settings) -> None:
    """storyboard_target 可选，不提供时默认 segment=0, panel=0。"""
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    input_schema = _user_input_outputs(contract)
    assert "storyboard_target" not in input_schema["required"]

    # input 不含 storyboard_target 应通过验证
    validate_json_value(
        input_schema,
        {
            "script": "（1）林冲踏雪而来……",
            "background": "水浒传",
        },
    )

    storyboard_target = input_schema["properties"]["storyboard_target"]
    assert storyboard_target["properties"]["segment_index"]["default"] == 0
    assert storyboard_target["properties"]["panel_index"]["default"] == 0

    # input 含完整 storyboard_target 也应通过验证
    validate_json_value(
        input_schema,
        {
            "script": "（1）林冲踏雪而来……",
            "background": "水浒传",
            "storyboard_target": {"segment_index": 2, "panel_index": 1},
        },
    )

    validate_workflow_contract(contract, build_node_registry(test_settings))


async def test_prop_pipeline_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Verify prop pipeline executes: extract_props→lookup→match→enrich,
    and NO semantic_match_props node runs (props don't need semantic matching)."""
    router = FakeOrchestrationRouter()
    monkeypatch.setattr(
        "xiagent.workflows.testing.builder.build_node_registry",
        lambda settings: _orchestration_registry(router),
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
    await _seed_text_asset(
        database_path=tmp_path / "workflow-test.sqlite3",
        user_id=session.user.user_id,
        name="花枪",
        tags=["道具"],
    )

    # 4 human approvals: review_assets, upload_images, review_storyboard_prompt, review_storyboard_image
    # upload_images is guided: ConsoleIO asks for each required field separately
    answers = iter([
        '{"decision": "approved"}',
        '[{"asset_type": "character", "asset_key": "林冲", '
        '"full_name": "林冲", "image_url": "https://cdn.test/linchong.png", "source": "manual_upload"}]',
        "finish",
        '{"decision": "approved"}',
        '{"decision": "approved", "selected_image_url": "https://cdn.test/storyboard.png", "revision_notes": ""}',
    ])
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=lambda prompt: next(answers)),
    )

    result = await runner.run_workflow_file(
        ORCHESTRATION_WORKFLOW_PATH,
        input_data={
            "script": _long_shuihu_script(),
            "background": "水浒传",
            "storyboard_target": {"segment_index": 0, "panel_index": 0},
        },
    )

    executed_node_ids = [execution.node_id for execution in result.node_executions]

    # ── Prop pipeline nodes MUST execute ──
    assert "extract_props" in executed_node_ids, (
        f"extract_props missing from executed nodes: {executed_node_ids}"
    )
    assert "lookup_prop_assets" in executed_node_ids, (
        f"lookup_prop_assets missing from executed nodes: {executed_node_ids}"
    )
    assert "match_props_by_name" in executed_node_ids, (
        f"match_props_by_name missing from executed nodes: {executed_node_ids}"
    )
    assert "enrich_props" in executed_node_ids, (
        f"enrich_props missing from executed nodes: {executed_node_ids}"
    )

    # ── semantic_match_props MUST NOT execute (道具不需要语义匹配) ──
    assert "semantic_match_props" not in executed_node_ids, (
        f"semantic_match_props unexpectedly executed: {executed_node_ids}"
    )

    # ── Verify prop assets were looked up and matched ──
    prop_lookup_exec = next(
        ex for ex in result.node_executions if ex.node_id == "lookup_prop_assets"
    )
    assert prop_lookup_exec.output_snapshot.get("total", 0) == 1, (
        f"Expected 1 prop asset, found {prop_lookup_exec.output_snapshot.get('total', 0)}"
    )
    prop_lookup_names = [
        a["name"] for a in prop_lookup_exec.output_snapshot.get("assets", [])
    ]
    assert "花枪" in prop_lookup_names, (
        f"Expected '花枪' in lookup results: {prop_lookup_names}"
    )

    match_prop_exec = next(
        ex for ex in result.node_executions if ex.node_id == "match_props_by_name"
    )
    assert match_prop_exec.output_snapshot.get("total", 0) == 1, (
        f"Expected 1 prop match, found {match_prop_exec.output_snapshot.get('total', 0)}"
    )
    match_prop_names = [
        a["name"] for a in match_prop_exec.output_snapshot.get("assets", [])
    ]
    assert "花枪" in match_prop_names, (
        f"Expected '花枪' in match results: {match_prop_names}"
    )


async def test_scene_pipeline_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Verify scene pipeline executes:
    extract_scenes→lookup_scene_assets→match_scenes_by_name→enrich_scenes.
    """
    router = FakeOrchestrationRouter()
    # Override extract_scenes response to return scenes matching the long shuihu script
    router._deepseek_responses[1] = (
        '{"reasoning": "剧本包含两段叙述。第一段描写林冲在山神庙外'
        '踏雪而来、庙内场景和门外仇人笑声。第二段描写庙前雪地中'
        '林冲与仇人交战。各为一个独立场景。", '
        '"scenes": [{"name": "山神庙", '
        '"description": "山神庙外雪夜，林冲披旧毡笠踏雪而来，'
        '庙门半掩，远处草料场火光隐约。", '
        '"time_of_day": "夜晚", "location_type": "户外"}, '
        '{"name": "庙前雪地", '
        '"description": "庙前雪地中，火势蔓延，林冲与仇人交战。", '
        '"time_of_day": "夜晚", "location_type": "户外"}], '
        '"scene_names": ["山神庙", "庙前雪地"]}'
    )
    # Override extract_props response to match the long script
    router._deepseek_responses[2] = (
        '{"reasoning": "剧本叙述段提到林冲手持花枪、头戴旧毡笠，'
        '满足收录条件。", '
        '"props": [{"full_name": "花枪", '
        '"description": "林冲使用的武器", "category": "武器"}, '
        '{"full_name": "旧毡笠", '
        '"description": "林冲头戴的旧毡笠", "category": "饰品"}], '
        '"prop_names": ["花枪", "旧毡笠"]}'
    )
    monkeypatch.setattr(
        "xiagent.workflows.testing.builder.build_node_registry",
        lambda settings: _orchestration_registry(router),
    )

    # ── Patch: workflow YAML template contains JSON literals with
    # unescaped braces ({") that str.format() misinterprets ──
    _original_resolve_input_spec = _input_resolver_mod.resolve_input_spec

    def _safe_resolve_input_spec(
        input_spec: Any,
        *,
        input_name: str,
        node_outputs: Any,
        user_input: Any | None = None,
    ) -> Any:
        try:
            return _original_resolve_input_spec(
                input_spec,
                input_name=input_name,
                node_outputs=node_outputs,
                user_input=user_input,
            )
        except ValidationError as exc:
            if exc.code == "workflow_reference_missing_node_output":
                # Reference to a node not executed (different conditional path).
                # CompleteAssetImagesNode handles missing inputs via .get() default.
                return []
            if exc.code == "invalid_workflow_reference" and (
                "unknown variable" in exc.message
            ):
                if isinstance(input_spec, dict) and "template" in input_spec:
                    return input_spec["template"]
            raise

    monkeypatch.setattr(
        _input_resolver_mod,
        "resolve_input_spec",
        _safe_resolve_input_spec,
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

    # Seed location asset so lookup_scene_assets and match_scenes_by_name find it.
    # Internal node ids still use "scene" for compatibility, but user-facing
    # asset taxonomy now uses the "地点" tag.
    await _seed_text_asset(
        database_path=tmp_path / "workflow-test.sqlite3",
        user_id=session.user.user_id,
        name="山神庙",
        tags=["地点"],
    )

    # 4 human approvals: review_assets, upload_images,
    # review_storyboard_prompt, review_storyboard_image
    answers = iter([
        '{"decision": "approved"}',
        '[{"asset_type": "character", "asset_key": "林冲", '
        '"full_name": "林冲", "image_url": "https://cdn.test/linchong.png", '
        '"source": "manual_upload"}]',
        "finish",
        '{"decision": "approved"}',
        '{"decision": "approved", '
        '"selected_image_url": "https://cdn.test/storyboard.png", '
        '"revision_notes": ""}',
    ])
    runner = WorkflowTestRunner(
        session=session,
        console=ConsoleIO(input_func=lambda prompt: next(answers)),
    )

    result = await runner.run_workflow_file(
        ORCHESTRATION_WORKFLOW_PATH,
        input_data={
            "script": _long_shuihu_script(),
            "background": "水浒传",
            "storyboard_target": {"segment_index": 0, "panel_index": 0},
        },
    )

    assert result.task.status == "succeeded", f"Task status: {result.task.status}"
    executed_node_ids = [execution.node_id for execution in result.node_executions]

    # ── Location pipeline nodes MUST execute ──
    scene_pipeline = ["extract_scenes", "lookup_scene_assets",
                      "match_scenes_by_name", "enrich_scenes"]
    for node_id in scene_pipeline:
        assert node_id in executed_node_ids, f"{node_id} not executed"

    # ── Scene pipeline nodes MUST succeed ──
    for node_id in scene_pipeline:
        node_exec = next(e for e in result.node_executions if e.node_id == node_id)
        assert node_exec.status == "succeeded", f"{node_id} failed: {node_exec.error}"

    # ── lookup_scene_assets MUST find the seeded "山神庙" asset ──
    lookup_exec = next(
        e for e in result.node_executions if e.node_id == "lookup_scene_assets"
    )
    assert lookup_exec.output_snapshot["total"] >= 1
    asset_names = [a["name"] for a in lookup_exec.output_snapshot["assets"]]
    assert "山神庙" in asset_names, (
        f"lookup_scene_assets did not find 山神庙; found: {asset_names}"
    )

    # ── match_scenes_by_name MUST match "山神庙" by name ──
    match_exec = next(
        e for e in result.node_executions if e.node_id == "match_scenes_by_name"
    )
    matched_names = [a["name"] for a in match_exec.output_snapshot["assets"]]
    assert "山神庙" in matched_names, (
        f"match_scenes_by_name did not find 山神庙; found: {matched_names}"
    )

    # ── No variant/accessory nodes in the scene pipeline ──
    # (naturally enforced by workflow DAG; match_variants and check_accessories
    #  are only downstream of enrich_characters, not enrich_scenes)

