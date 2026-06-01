from __future__ import annotations

import pytest
from typing import Any

from xiagent.core.errors import ConflictError, ValidationError
from xiagent.nodes import build_node_registry
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.system.user_choice import SystemUserChoiceNode
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.nodes.tools.complete_asset_images import CompleteAssetImagesNode
from xiagent.nodes.tools.enrich_characters import EnrichCharactersNode
from xiagent.nodes.tools.episode_metadata import (
    EpisodeMetadataFinalizeNode,
    EpisodeMetadataFromAssetNode,
)
from xiagent.nodes.tools.filter_assets_for_generation import FilterAssetsForGenerationNode
from xiagent.nodes.tools.merge_segment_storyboard_descriptions import (
    MergeSegmentStoryboardDescriptionsNode,
)
from xiagent.nodes.tools.prepare_segment_storyboard_inputs import (
    PrepareSegmentStoryboardInputsNode,
)
from xiagent.nodes.tools.prepare_storyboard_panel_cards import (
    PrepareStoryboardPanelCardsNode,
)
from xiagent.nodes.tools.resolve_accessory_asset_refs import ResolveAccessoryAssetRefsNode
from xiagent.nodes.tools.resolve_character_variant_refs import ResolveCharacterVariantRefsNode
from xiagent.nodes.tools.resolve_segment_image_refs import ResolveSegmentImageRefsNode


def test_register_and_get_node() -> None:
    registry = NodeRegistry()
    node = HumanApprovalNode()
    registry.register(node)
    assert registry.get("system.human_approval.v1") is node


def test_duplicate_node_ref_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    with pytest.raises(ConflictError):
        registry.register(HumanApprovalNode())


def test_registering_non_base_node_is_rejected() -> None:
    registry = NodeRegistry()

    with pytest.raises(TypeError):
        registry.register(object())  # type: ignore[arg-type]


def test_list_returns_nodes_in_registration_order() -> None:
    registry = NodeRegistry()
    human_node = HumanApprovalNode()
    echo_node = EchoToolNode()

    registry.register(human_node)
    registry.register(echo_node)

    assert registry.list() == [human_node, echo_node]


def test_build_node_registry_registers_builtin_nodes(test_settings) -> None:
    registry = build_node_registry(test_settings)

    refs = {node.describe().ref for node in registry.list()}

    assert refs == {
        "system.human_approval.v1",
        "system.user_choice.v1",
        "system.user_input.v1",
        "tool.echo.v1",
        "tool.script_split.v1",
        "tool.assemble_segment_context.v1",
        "tool.assemble_storyboard_context.v1",
        "tool.asset_lookup.v1",
        "tool.create_text_asset.v1",
        "tool.episode_metadata_finalize.v1",
        "tool.episode_metadata_from_asset.v1",
        "tool.enrich_characters.v1",
        "tool.filter_assets_for_generation.v1",
        "tool.resolve_accessory_asset_refs.v1",
        "tool.resolve_character_variant_refs.v1",
        "tool.resolve_segment_image_refs.v1",
        "tool.extract_panel_image_urls.v1",
        "tool.runninghub_workflow_images.v1",
        "tool.storyboard_prompt_assembler.v1",
        "tool.storyboard_prompt_assembler.v2",
        "tool.merge_segment_storyboard_descriptions.v1",
        "tool.prepare_segment_storyboard_inputs.v1",
        "tool.prepare_storyboard_panel_cards.v1",
        "ai.assign_assets_to_segments.v1",
        "ai.deepseek_chat.v1",
        "ai.deepseek_structured_json.v1",
        "ai.asset_draft_from_description.v1",
        "ai.asset_metadata_from_upload.v1",
        "ai.parallel_deepseek_structured_json.v1",
        "ai.runninghub_image_to_image.v1",
        "ai.runninghub_image_to_image.v2",
        "ai.runninghub_image_to_image.v3",
        "ai.runninghub_text_to_image.v1",
        "ai.gemini_vision.v1",
        "tool.merge_asset_images.v1",
        "tool.complete_asset_images.v1",
    }


async def test_filter_assets_for_generation_removes_existing_assets() -> None:
    node = FilterAssetsForGenerationNode()

    result = await node.run(
        None,
        {
            "approved_assets": {
                "characters": [
                    {
                        "type": "character",
                        "name": "林冲",
                        "matched": True,
                        "matched_asset_id": "asset-linchong",
                        "matched_asset_name": "林冲",
                    },
                    {
                        "type": "character",
                        "name": "鲁智深",
                        "matched": False,
                        "matched_asset_id": None,
                        "matched_asset_name": "",
                    },
                ],
                "assets": [
                    {"type": "asset", "name": "野猪林", "matched": True, "matched_asset_name": "野猪林"},
                    {"type": "asset", "name": "山神庙", "matched": False},
                ],
                "props": [
                    {"type": "prop", "name": "水火棍", "matched": False},
                ],
            }
        },
    )

    assert result.output["asset_count"] == 3
    assert [item["name"] for item in result.output["approved_assets"]["characters"]] == ["鲁智深"]
    assert [item["name"] for item in result.output["approved_assets"]["assets"]] == ["山神庙"]
    assert [item["name"] for item in result.output["approved_assets"]["props"]] == ["水火棍"]


async def test_filter_assets_for_generation_keeps_explicit_reference_context() -> None:
    node = FilterAssetsForGenerationNode()
    ctx = NodeContext(
        user_id="user-1",
        project_id="project-1",
        task_id="task-1",
        node_id="filter_assets_for_generation",
        node_execution_id="exec-1",
        config={},
        output_schema={},
        asset_service=None,
        event_sink=None,
        logger=None,
    )

    result = await node.run(
        ctx,
        {
            "approved_assets": {
                "characters": [
                    {
                        "type": "character",
                        "name": "鲁智深",
                        "reference_image_ref": {"kind": "asset", "asset_id": "variant-ref", "role": "reference"},
                        "reference_appearance_description": "僧衣参考图外貌。",
                    }
                ],
                "assets": [{"type": "location", "name": "野猪林"}],
                "props": [{"type": "prop", "name": "禅杖"}],
            },
        },
    )

    output = result.output["approved_assets"]
    assert output["characters"][0]["reference_image_ref"] == {
        "kind": "asset",
        "asset_id": "variant-ref",
        "role": "reference",
    }
    assert output["characters"][0]["reference_variant_description"] == "僧衣参考图外貌。"
    assert "reference_image_ref" not in output["assets"][0]
    assert "reference_source" not in output["assets"][0]
    assert "reference_image_ref" not in output["props"][0]
    assert "reference_source" not in output["props"][0]


async def test_resolve_character_variant_refs_inherits_variant_facts_programmatically() -> None:
    node = ResolveCharacterVariantRefsNode()

    result = await node.run(
        None,
        {
            "characters": [
                {
                    "full_name": "林冲",
                    "existing_variants": [
                        {
                            "asset_id": "variant-default",
                            "variant": "默认",
                            "storage_uri": "https://cdn.test/default.png",
                            "appearance_description": "默认官服参考图外貌。",
                            "metadata": {"status": "八十万禁军教头，身着官服。"},
                        },
                        {
                            "asset_id": "variant-prisoner",
                            "variant": "囚服",
                            "image_url": "https://cdn.test/prisoner.png",
                            "appearance_description": "囚服参考图外貌。",
                            "metadata": {"status": "刺配途中，身着囚服。"},
                        },
                    ],
                },
                {
                    "full_name": "鲁智深",
                    "existing_variants": [
                        {
                            "asset_id": "variant-monk",
                            "variant": "僧衣",
                            "appearance_description": "僧衣参考图外貌。",
                        }
                    ],
                },
            ],
            "variant_results": [
                {
                    "full_name": "林冲",
                    "accessories": ["毡笠"],
                    "matched_variant": "囚服",
                    "matched_variant_id": None,
                    "is_new_variant": False,
                    "new_variant_name": "",
                    "default_variant_status": "LLM 编造状态",
                    "default_variant_storage_uri": "https://bad.test/fake.png",
                    "default_variant_appearance_description": "LLM 编造默认图描述",
                    "matched_variant_appearance_description": "LLM 编造匹配图描述",
                    "reason": "已有囚服",
                },
                {
                    "full_name": "鲁智深",
                    "accessories": [],
                    "matched_variant": "僧衣",
                    "matched_variant_id": None,
                    "is_new_variant": False,
                    "new_variant_name": "",
                    "reason": "已有僧衣",
                },
            ],
        },
    )

    resolved = result.output["results"][0]
    assert resolved["matched_variant_id"] == "variant-prisoner"
    assert resolved["default_variant_status"] == "八十万禁军教头，身着官服。"
    assert resolved["default_variant_storage_uri"] == "https://cdn.test/default.png"
    assert resolved["default_variant_appearance_description"] == "默认官服参考图外貌。"
    assert resolved["matched_variant_appearance_description"] == "囚服参考图外貌。"
    no_default = result.output["results"][1]
    assert no_default["matched_variant_id"] == "variant-monk"
    assert no_default["default_variant_status"] == ""
    assert no_default["default_variant_storage_uri"] == ""
    assert no_default["default_variant_appearance_description"] == ""
    assert no_default["matched_variant_appearance_description"] == "僧衣参考图外貌。"


def test_resolve_segment_image_refs_descriptor() -> None:
    descriptor = ResolveSegmentImageRefsNode().describe()

    assert descriptor.ref == "tool.resolve_segment_image_refs.v1"
    assert descriptor.kind == "tool"
    assert descriptor.input_schema["required"] == ["segment_assignments", "asset_catalog"]
    assert descriptor.output_schema["required"] == ["segment_assignments"]


def test_segment_storyboard_tool_descriptors() -> None:
    prepare_descriptor = PrepareSegmentStoryboardInputsNode().describe()
    merge_descriptor = MergeSegmentStoryboardDescriptionsNode().describe()
    panel_cards_descriptor = PrepareStoryboardPanelCardsNode().describe()

    assert prepare_descriptor.ref == "tool.prepare_segment_storyboard_inputs.v1"
    assert prepare_descriptor.kind == "tool"
    assert prepare_descriptor.input_schema["required"] == [
        "source_script",
        "segments",
        "segment_assignments",
    ]
    assert merge_descriptor.ref == "tool.merge_segment_storyboard_descriptions.v1"
    assert merge_descriptor.kind == "tool"
    assert merge_descriptor.output_schema["required"] == ["segment_descriptions"]
    assert panel_cards_descriptor.ref == "tool.prepare_storyboard_panel_cards.v1"
    assert panel_cards_descriptor.kind == "tool"
    assert panel_cards_descriptor.output_schema["required"] == ["panel_cards"]


async def test_prepare_storyboard_panel_cards_builds_cards() -> None:
    node = PrepareStoryboardPanelCardsNode()

    result = await node.run(
        None,
        {
            "segment_descriptions": [
                {
                    "index": 0,
                    "segment_title": "雪夜",
                    "thinking": "风雪推进。",
                    "panels": [
                        {
                            "description": "林冲踏雪前行。",
                            "style": "国风漫画",
                            "constraints": "保持囚服和毡笠。",
                        }
                    ],
                }
            ],
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "location": "野猪林",
                    "characters": [
                        {
                            "full_name": "林冲",
                            "variant": "囚服",
                            "image_ref": {"kind": "asset", "asset_id": "asset-linchong", "role": "reference"},
                        }
                    ],
                    "key_props": ["花枪"],
                }
            ],
            "storyboard_items": [{"index": 0, "current_segment": {"text": "林冲踏雪。"}}],
            "shared_context": {"full_script": "完整剧本", "all_segments": []},
        },
    )

    card = result.output["panel_cards"][0]
    assert card["card_id"] == "segment-0-panel-0"
    assert card["reference_assets"][0]["full_name"] == "林冲"
    assert card["image_refs"] == [{"kind": "asset", "asset_id": "asset-linchong", "role": "reference"}]
    assert "林冲踏雪前行" in card["prompt"]
    assert "出场角色：林冲（囚服）" in card["prompt"]


async def test_resolve_accessory_asset_refs_uses_match_or_first_variant_asset() -> None:
    node = ResolveAccessoryAssetRefsNode()

    result = await node.run(
        None,
        {
            "characters": [
                {
                    "full_name": "林冲",
                    "existing_variants": [
                        {
                            "asset_id": "variant-prisoner-base",
                            "name": "林冲_囚服",
                            "variant": "囚服",
                            "storage_uri": "https://cdn.test/prisoner-base.png",
                            "appearance_description": "囚服基础参考图。",
                            "tags": ["角色", "林冲", "囚服"],
                        },
                        {
                            "asset_id": "variant-prisoner-hat",
                            "name": "林冲_囚服_毡笠",
                            "variant": "囚服",
                            "storage_uri": "https://cdn.test/prisoner-hat.png",
                            "appearance_description": "囚服加毡笠参考图。",
                            "tags": ["角色", "林冲", "囚服", "毡笠"],
                        },
                    ],
                },
            ],
            "variant_results": [
                {
                    "full_name": "林冲",
                    "matched_variant": "囚服",
                    "matched_variant_id": "variant-prisoner-base",
                }
            ],
            "accessory_results": [
                {
                    "full_name": "林冲",
                    "existing_accessories": ["毡笠"],
                    "new_accessories": ["披风"],
                    "has_new_accessories": True,
                    "reason": "毡笠已存在，披风未命中。",
                }
            ],
        },
    )

    selected = result.output["results"][0]["selected_accessory_assets"]
    assert selected == [
        {
            "accessory": "毡笠",
            "matched": True,
            "asset_id": "variant-prisoner-hat",
            "asset_name": "林冲_囚服_毡笠",
            "asset_ref": {"kind": "asset", "asset_id": "variant-prisoner-hat", "role": "reference"},
            "storage_uri": "https://cdn.test/prisoner-hat.png",
            "appearance_description": "囚服加毡笠参考图。",
            "source": "matched_accessory",
        },
        {
            "accessory": "披风",
            "matched": False,
            "asset_id": "variant-prisoner-base",
            "asset_name": "林冲_囚服",
            "asset_ref": {"kind": "asset", "asset_id": "variant-prisoner-base", "role": "reference"},
            "storage_uri": "https://cdn.test/prisoner-base.png",
            "appearance_description": "囚服基础参考图。",
            "source": "first_variant_asset",
        },
    ]


async def test_episode_metadata_nodes_roundtrip_payload() -> None:
    class FakeAsset:
        def __init__(self, *, asset_id: str, name: str, text_content: str, metadata: dict[str, Any]) -> None:
            self.asset_id = asset_id
            self.name = name
            self.text_content = text_content
            self.metadata = metadata

    class FakeAssetContent:
        def __init__(self, text_content: str) -> None:
            self.text_content = text_content

    class FakeSearchResult:
        def __init__(self, items: list[FakeAsset]) -> None:
            self.items = items

    class FakeAssetService:
        def __init__(self) -> None:
            self.created: dict[str, FakeAsset] = {}

        async def create_text_asset(self, **kwargs: Any) -> FakeAsset:
            asset = FakeAsset(
                asset_id="asset-episode",
                name=kwargs["name"],
                text_content=kwargs["text"],
                metadata=kwargs["metadata"],
            )
            self.created[asset.asset_id] = asset
            return asset

        async def get_asset(self, **kwargs: Any) -> FakeAsset:
            return self.created[kwargs["asset_id"]]

        async def get_asset_content(self, **kwargs: Any) -> FakeAssetContent:
            return FakeAssetContent(self.created[kwargs["asset_id"]].text_content)

        async def search_assets(self, **kwargs: Any) -> FakeSearchResult:
            return FakeSearchResult([])

    service = FakeAssetService()
    ctx = NodeContext(
        user_id="user-1",
        project_id="project-1",
        task_id="task-1",
        node_id="finish_summary",
        node_execution_id="exec-1",
        config={},
        output_schema={},
        asset_service=service,  # type: ignore[arg-type]
        event_sink=None,
        logger=None,
    )

    result = await EpisodeMetadataFinalizeNode().run(
        ctx,
        {
            "episode_name": "23、私放晁天王",
            "episode_summary": "晁盖义释刘唐，宋江暗通消息。",
            "source_script": "宋江见了晁盖。",
            "asset_catalog": {"characters": [{"name": "宋江"}], "assets": [], "props": []},
            "asset_images": [{"full_name": "宋江", "asset_id": "asset-songjiang"}],
            "prompt_results": [],
        },
    )
    loaded = await EpisodeMetadataFromAssetNode().run(
        ctx,
        {"episode_asset_id": result.output["episode_asset_id"]},
    )

    assert service.created["asset-episode"].metadata["type"] == "episode_metadata"
    assert "tags" not in service.created["asset-episode"].metadata
    assert loaded.output["episode_name"] == "23、私放晁天王"
    assert loaded.output["source_script"] == "宋江见了晁盖。"
    assert result.output["asset_images"] == [{"full_name": "宋江", "asset_id": "asset-songjiang"}]
    assert loaded.output["asset_catalog"]["approved_assets"]["characters"][0]["name"] == "宋江"
    assert loaded.asset_refs[0].asset_id == "asset-episode"


async def test_complete_asset_images_prepares_only_missing_prompts() -> None:
    node = CompleteAssetImagesNode()

    result = await node.run(
        None,
        {
            "decision": "generate_missing",
            "prompt_results": [
                {"full_name": "林冲", "prompt": "生成林冲", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
                {"full_name": "鲁智深", "prompt": "生成鲁智深", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
            ],
            "manual_images": ["https://cdn.test/linchong.png"],
        },
    )

    assert result.output["next_action"] == "generate_missing"
    assert result.output["missing_count"] == 1
    assert result.output["asset_images"] == [
        {
            "full_name": "林冲",
            "image_url": "https://cdn.test/linchong.png",
            "source": "manual_upload",
        }
    ]
    assert result.output["missing_prompt_results"] == [
        {"full_name": "鲁智深", "prompt": "生成鲁智深", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}}
    ]


async def test_complete_asset_images_matches_uploaded_cards_by_asset_key() -> None:
    node = CompleteAssetImagesNode()

    result = await node.run(
        None,
        {
            "decision": "generate_missing",
            "prompt_results": [
                {"full_name": "林冲", "prompt": "生成林冲", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
                {"full_name": "鲁智深", "prompt": "生成鲁智深", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
            ],
            "manual_images": [
                {
                    "asset_type": "character",
                    "asset_key": "鲁智深",
                    "full_name": "鲁智深",
                    "image_url": "https://cdn.test/luzhishen.png",
                    "source": "manual_upload",
                }
            ],
        },
    )

    assert result.output["next_action"] == "generate_missing"
    assert result.output["missing_count"] == 1
    assert result.output["missing_prompt_results"] == [
        {"full_name": "林冲", "prompt": "生成林冲", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}}
    ]


async def test_complete_asset_images_matches_prefixed_asset_key_by_full_name() -> None:
    node = CompleteAssetImagesNode()

    result = await node.run(
        None,
        {
            "decision": "generate_missing",
            "prompt_results": [
                {"full_name": "花枪", "prompt": "生成花枪", "reference_image_ref": {"kind": "asset", "asset_id": "prop-ref", "role": "reference"}},
            ],
            "manual_images": [
                {
                    "asset_type": "prop",
                    "asset_key": "prop:花枪",
                    "full_name": "花枪",
                    "image_url": "https://cdn.test/huagang.png",
                    "source": "manual_upload",
                }
            ],
        },
    )

    assert result.output["next_action"] == "finish"
    assert result.output["missing_count"] == 0
    assert result.output["missing_prompt_results"] == []


async def test_complete_asset_images_targets_single_card_for_regeneration() -> None:
    node = CompleteAssetImagesNode()

    result = await node.run(
        None,
        {
            "decision": "generate_missing",
            "target_asset_key": "鲁智深",
            "prompt_results": [
                {"full_name": "林冲", "prompt": "生成林冲", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
                {"full_name": "鲁智深_僧衣", "prompt": "生成鲁智深僧衣", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
                {"full_name": "水火棍", "prompt": "生成水火棍", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
            ],
            "manual_images": [
                {
                    "asset_type": "character",
                    "asset_key": "林冲",
                    "full_name": "林冲",
                    "image_url": "https://cdn.test/linchong.png",
                    "source": "manual_upload",
                }
            ],
        },
    )

    assert result.output["next_action"] == "generate_missing"
    assert result.output["missing_count"] == 1
    assert result.output["missing_prompt_results"] == [
        {"full_name": "鲁智深_僧衣", "prompt": "生成鲁智深僧衣", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}}
    ]


async def test_enrich_characters_carries_matched_asset_ref() -> None:
    node = EnrichCharactersNode()

    result = await node.run(
        None,
        {
            "characters": [{"full_name": "花枪", "description": "林冲使用的长枪"}],
            "matched_by_name": [
                {
                    "asset_id": "asset_prop_1",
                    "name": "花枪",
                    "metadata": {
                        "public_url": "https://cdn.test/huagang-ref.png",
                        "appearance_description": "一杆银亮花枪，红缨醒目，枪身细长。",
                    },
                }
            ],
        },
    )

    assert result.output["characters"][0]["matched_asset_ref"] == {
        "kind": "asset",
        "asset_id": "asset_prop_1",
        "role": "reference",
    }
    assert result.output["characters"][0]["matched_asset_appearance_description"] == "一杆银亮花枪，红缨醒目，枪身细长。"
    assert result.output["characters"][0]["reference_appearance_description"] == "一杆银亮花枪，红缨醒目，枪身细长。"


async def test_complete_asset_images_merges_manual_and_generated_images() -> None:
    node = CompleteAssetImagesNode()

    result = await node.run(
        None,
        {
            "decision": "finish",
            "manual_images": [
                {"full_name": "林冲", "image_url": "https://cdn.test/linchong.png", "source": "manual_upload"}
            ],
            "auto_images": [
                {"full_name": "鲁智深", "image_url": "https://cdn.test/luzhishen.png", "source": "ai_generated"}
            ],
        },
    )

    assert result.output["next_action"] == "finish"
    assert result.output["missing_count"] == 0
    assert result.output["asset_images"] == [
        {"full_name": "林冲", "image_url": "https://cdn.test/linchong.png", "source": "manual_upload"},
        {"full_name": "鲁智深", "image_url": "https://cdn.test/luzhishen.png", "source": "ai_generated"},
    ]


class UiDefaultProbeNode(BaseNode):
    def __init__(self, *, ui_defaults: dict | None = None) -> None:
        self._ui_defaults = ui_defaults or {}

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.ui_default_probe.v1",
            name="UI Default Probe",
            version="1.0.0",
            kind="test",
            input_schema={
                "type": "object",
                "properties": {
                    "candidates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "image_url": {"type": "string"},
                            },
                        },
                    }
                },
            },
            output_schema={"type": "object"},
            ui_defaults=self._ui_defaults,
        )

    async def run(self, ctx: NodeContext | None, inputs: dict) -> NodeResult:
        return NodeResult(status="succeeded", output={})


def test_register_node_with_valid_ui_defaults() -> None:
    registry = NodeRegistry()

    registry.register(
        UiDefaultProbeNode(
            ui_defaults={
                "controls": {
                    "interaction": {
                        "control_id": "ui.choice.image_three.v1",
                        "variant": "equal_grid",
                        "mode": "interactive",
                        "bindings": {
                            "items_path": "$node.input.candidates",
                            "image_url_path": "image_url",
                            "value_path": "id",
                        },
                    }
                }
            }
        )
    )

    assert registry.get("test.ui_default_probe.v1").describe().ui_defaults


def test_register_node_rejects_unknown_ui_default_control() -> None:
    registry = NodeRegistry()

    with pytest.raises(ValidationError) as exc_info:
        registry.register(
            UiDefaultProbeNode(
                ui_defaults={
                    "controls": {
                        "interaction": {
                            "control_id": "ui.missing.v1",
                            "variant": "default",
                            "mode": "interactive",
                            "bindings": {},
                        }
                    }
                }
            )
        )

    assert exc_info.value.code == "unknown_ui_control"


def test_register_node_rejects_ui_default_missing_binding() -> None:
    registry = NodeRegistry()

    with pytest.raises(ValidationError) as exc_info:
        registry.register(
            UiDefaultProbeNode(
                ui_defaults={
                    "controls": {
                        "interaction": {
                            "control_id": "ui.choice.image_three.v1",
                            "variant": "equal_grid",
                            "mode": "interactive",
                            "bindings": {"items_path": "$node.input.candidates"},
                        }
                    }
                }
            )
        )

    assert exc_info.value.code == "missing_ui_binding"


async def test_user_choice_node_waits_with_candidates_metadata() -> None:
    node = SystemUserChoiceNode()
    candidates = [{"id": "a", "image_url": "https://example.test/a.png"}]

    result = await node.run(ctx=None, inputs={"question": "选择一张", "candidates": candidates})

    assert result.status == "waiting"
    assert result.output == {}
    assert result.metadata == {
        "question": "选择一张",
        "candidates": candidates,
        "selection_mode": "single",
    }


async def test_user_input_node_returns_inputs_with_schema_form_defaults() -> None:
    from xiagent.nodes.system.user_input import SystemUserInputNode

    inputs = {"prompt": "雨夜城市", "image_urls": ["https://example.test/a.png"]}

    result = await SystemUserInputNode().run(ctx=None, inputs=inputs)
    descriptor = SystemUserInputNode().describe()

    assert result.status == "succeeded"
    assert result.output == inputs
    assert descriptor.ui_defaults["controls"]["input"] == {
        "control_id": "ui.input.schema_form.v1",
        "variant": "default",
        "mode": "input",
    }
    assert descriptor.ui_defaults["controls"]["output"] == {
        "control_id": "ui.input.schema_form.v1",
        "variant": "default",
        "mode": "readonly",
    }


def test_build_node_registry_uses_settings_deepseek_model(test_settings) -> None:
    from dataclasses import replace

    registry = build_node_registry(
        replace(
            test_settings,
            deepseek_api_key="settings-test-key",
            deepseek_base_url="https://settings.deepseek.test",
            deepseek_model="settings-model",
        )
    )

    deepseek_node = registry.get("ai.deepseek_chat.v1")

    assert deepseek_node._model == "settings-model"  # noqa: SLF001


def test_build_node_registry_uses_settings_runninghub_models(test_settings) -> None:
    from dataclasses import replace

    registry = build_node_registry(
        replace(
            test_settings,
            runninghub_image_api_key="settings-runninghub-key",
            runninghub_image_base_url="https://settings.runninghub.test",
            runninghub_image_model="settings-image-model",
            runninghub_image_endpoint="/settings/image-to-image",
            runninghub_image_default_aspect_ratio="4:3",
            runninghub_image_default_resolution="2K",
            runninghub_image_poll_interval_seconds=0.1,
            runninghub_image_poll_timeout_seconds=1.0,
            runninghub_text_to_image_api_key="settings-runninghub-key",
            runninghub_text_to_image_base_url="https://settings.runninghub.test",
            runninghub_text_to_image_model="settings-text-model",
            runninghub_text_to_image_endpoint="/settings/text-to-image",
            runninghub_text_to_image_default_aspect_ratio="1:1",
            runninghub_text_to_image_default_resolution="4K",
            runninghub_text_to_image_poll_interval_seconds=0.1,
            runninghub_text_to_image_poll_timeout_seconds=1.0,
        )
    )

    image_node = registry.get("ai.runninghub_image_to_image.v1")
    text_node = registry.get("ai.runninghub_text_to_image.v1")

    assert image_node._provider == "runninghub_image"  # noqa: SLF001
    assert image_node._model == "settings-image-model"  # noqa: SLF001
    assert text_node._provider == "runninghub_text_to_image"  # noqa: SLF001
    assert text_node._model == "settings-text-model"  # noqa: SLF001

    image_provider = image_node._model_router._providers["runninghub_image"]  # noqa: SLF001
    text_provider = text_node._model_router._providers["runninghub_text_to_image"]  # noqa: SLF001
    assert image_provider._config.default_aspect_ratio == "4:3"  # noqa: SLF001
    assert image_provider._config.default_resolution == "2K"  # noqa: SLF001
    assert text_provider._config.default_aspect_ratio == "1:1"  # noqa: SLF001
    assert text_provider._config.default_resolution == "4K"  # noqa: SLF001


def test_node_context_asset_service_is_core_service_interface() -> None:
    from typing import get_type_hints

    from xiagent.core.services import AssetService
    from xiagent.nodes.base import NodeContext

    hints = get_type_hints(NodeContext)

    assert hints["asset_service"] == AssetService | None


async def test_human_approval_returns_waiting_with_requested_inputs() -> None:
    node = HumanApprovalNode()
    inputs = {"question": "Approve?", "context": {"risk": "low"}}

    result = await node.run(ctx=None, inputs=inputs)

    assert result.status == "waiting"
    assert result.output == {}
    assert result.metadata["requested_inputs"] == inputs


async def test_human_approval_filters_success_output_to_declared_schema() -> None:
    node = HumanApprovalNode()
    ctx = NodeContext(
        user_id="user_1",
        project_id="project_1",
        task_id="task_1",
        node_id="review",
        node_execution_id="exec_1",
        config={},
        output_schema={
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string", "minLength": 1}},
            "additionalProperties": False,
        },
        asset_service=None,
        event_sink=None,
        logger=None,
    )

    result = await node.run(ctx=ctx, inputs={"question": "喜欢的颜色？", "answer": "蓝色"})

    assert result.status == "succeeded"
    assert result.output == {"answer": "蓝色"}


async def test_echo_tool_returns_inputs() -> None:
    node = EchoToolNode()
    inputs = {"message": "hello", "count": 2}

    result = await node.run(ctx=None, inputs=inputs)

    assert result.status == "succeeded"
    assert result.output == {"echo": inputs}
