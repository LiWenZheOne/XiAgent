from __future__ import annotations

import pytest
from typing import Any

from xiagent.core.errors import ConflictError, ValidationError
from xiagent.models import ChatModelRouter
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
from xiagent.nodes.tools.prepare_asset_semantic_match import PrepareAssetSemanticMatchNode
from xiagent.nodes.tools.prepare_storyboard_panel_cards import (
    PrepareStoryboardPanelCardsNode,
)
from xiagent.nodes.tools.prepare_storyboard_asset_index import (
    PrepareStoryboardAssetIndexNode,
)
from xiagent.nodes.tools.resolve_accessory_asset_refs import ResolveAccessoryAssetRefsNode
from xiagent.nodes.tools.resolve_character_variant_refs import ResolveCharacterVariantRefsNode
from xiagent.nodes.tools.resolve_segment_image_refs import ResolveSegmentImageRefsNode
from xiagent.nodes.ai.storyboard_review_refine import StoryboardReviewRefineNode


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
        "tool.prepare_asset_semantic_match.v1",
        "tool.prepare_storyboard_panel_cards.v1",
        "tool.prepare_storyboard_asset_index.v1",
        "ai.assign_assets_to_segments.v1",
        "ai.deepseek_chat.v1",
        "ai.deepseek_structured_json.v1",
        "ai.asset_draft_from_description.v1",
        "ai.asset_metadata_from_upload.v1",
        "ai.parallel_deepseek_structured_json.v1",
        "ai.storyboard_review_refine.v1",
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
            "prompts_per_item": 3,
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
                        "appearance_description": "浓眉圆眼，僧衣上身，脚穿布鞋，气质豪放，下半身为球形整体。",
                    },
                ],
                "assets": [
                    {"type": "asset", "name": "野猪林", "matched": True, "matched_asset_name": "野猪林"},
                    {"type": "asset", "name": "山神庙", "matched": False, "description": "雪夜破庙，梁木倾斜，门窗残旧。"},
                ],
                "props": [
                    {"type": "prop", "name": "水火棍", "matched": False, "description": "长直棍棒，两端颜色深。"},
                ],
            }
        },
    )

    assert result.output["asset_count"] == 3
    assert result.output["new_asset_count"] == 3
    assert result.output["matched_asset_count"] == 2
    assert result.output["has_assets_to_generate"] is True
    assert result.output["generation_summary"] == {
        "total_asset_count": 5,
        "new_asset_count": 3,
        "matched_asset_count": 2,
        "has_assets_to_generate": True,
    }
    assert [item["name"] for item in result.output["approved_assets"]["characters"]] == ["鲁智深"]
    assert [item["name"] for item in result.output["approved_assets"]["assets"]] == ["山神庙"]
    assert [item["name"] for item in result.output["approved_assets"]["props"]] == ["水火棍"]
    assert result.output["approved_assets"]["characters"][0]["prompts_per_item"] == 3
    assert result.output["approved_assets"]["assets"][0]["prompts_per_item"] == 3
    assert result.output["approved_assets"]["props"][0]["prompts_per_item"] == 3
    character_description = result.output["approved_assets"]["characters"][0]["target_appearance_description"]
    assert character_description == "浓眉圆眼，僧衣上身，气质豪放"
    assert "脚" not in character_description
    assert "鞋" not in character_description
    assert "下半身" not in character_description
    assert result.output["approved_assets"]["assets"][0]["target_appearance_description"] == "雪夜破庙，梁木倾斜，门窗残旧。"
    assert result.output["approved_assets"]["props"][0]["target_appearance_description"] == "长直棍棒，两端颜色深。"


async def test_filter_assets_for_generation_reports_empty_generation_branch() -> None:
    node = FilterAssetsForGenerationNode()

    result = await node.run(
        None,
        {
            "approved_assets": {
                "characters": [
                    {
                        "asset_type": "character",
                        "asset_name": "林冲",
                        "matched": True,
                        "matched_asset_id": "asset-linchong",
                        "matched_asset_name": "林冲",
                    }
                ],
                "assets": [
                    {
                        "asset_type": "scene",
                        "asset_name": "山神庙外",
                        "matched": True,
                        "matched_asset_id": "asset-temple",
                        "matched_asset_name": "山神庙外",
                    }
                ],
                "props": [],
            }
        },
    )

    assert result.output["approved_assets"] == {"characters": [], "assets": [], "props": []}
    assert result.output["asset_count"] == 0
    assert result.output["new_asset_count"] == 0
    assert result.output["matched_asset_count"] == 2
    assert result.output["has_assets_to_generate"] is False
    assert result.output["generation_summary"] == {
        "total_asset_count": 2,
        "new_asset_count": 0,
        "matched_asset_count": 2,
        "has_assets_to_generate": False,
    }


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
                        "asset_type": "character",
                        "asset_name": "鲁智深",
                        "asset_tags": ["僧衣"],
                        "reference_image_ref": {"kind": "asset", "asset_id": "variant-ref", "role": "reference"},
                        "reference_appearance_description": "僧衣参考图外貌。",
                    }
                ],
                "assets": [{"asset_type": "location", "asset_name": "野猪林", "asset_tags": []}],
                "props": [{"asset_type": "prop", "asset_name": "禅杖", "asset_tags": []}],
            },
        },
    )

    output = result.output["approved_assets"]
    assert output["characters"][0]["reference_image_ref"] == {
        "kind": "asset",
        "asset_id": "variant-ref",
        "role": "reference",
    }
    assert output["characters"][0]["reference_appearance_description"] == "僧衣参考图外貌。"
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
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "existing_variants": [
                        {
                            "asset_id": "variant-default",
                            "asset_tags": ["默认"],
                            "storage_uri": "https://cdn.test/default.png",
                            "appearance_description": "默认官服参考图外貌。",
                            "metadata": {"status": "八十万禁军教头，身着官服。"},
                        },
                        {
                            "asset_id": "variant-prisoner",
                            "asset_tags": ["囚服"],
                            "image_url": "https://cdn.test/prisoner.png",
                            "appearance_description": "囚服参考图外貌。",
                            "metadata": {"status": "刺配途中，身着囚服。"},
                        },
                    ],
                },
                {
                    "asset_type": "character",
                    "asset_name": "鲁智深",
                    "existing_variants": [
                        {
                            "asset_id": "variant-monk",
                            "asset_tags": ["僧衣"],
                            "appearance_description": "僧衣参考图外貌。",
                        }
                    ],
                },
            ],
            "variant_results": [
                {
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服"],
                    "matched_asset_id": "",
                    "default_asset_status": "LLM 编造状态",
                    "default_asset_storage_uri": "https://bad.test/fake.png",
                    "default_asset_appearance_description": "LLM 编造默认图描述",
                    "matched_asset_appearance_description": "LLM 编造匹配图描述",
                    "reason": "已有囚服",
                },
                {
                    "asset_type": "character",
                    "asset_name": "鲁智深",
                    "asset_tags": ["僧衣"],
                    "matched_asset_id": "",
                    "reason": "已有僧衣",
                },
            ],
        },
    )

    resolved = result.output["results"][0]
    assert resolved["matched_asset_id"] == "variant-prisoner"
    assert resolved["default_asset_status"] == "八十万禁军教头，身着官服。"
    assert resolved["default_asset_storage_uri"] == "https://cdn.test/default.png"
    assert resolved["default_asset_appearance_description"] == "默认官服参考图外貌。"
    assert resolved["matched_asset_appearance_description"] == "囚服参考图外貌。"
    no_default = result.output["results"][1]
    assert no_default["matched_asset_id"] == "variant-monk"
    assert no_default["default_asset_status"] == ""
    assert no_default["default_asset_storage_uri"] == ""
    assert no_default["default_asset_appearance_description"] == "僧衣参考图外貌。"
    assert no_default["matched_asset_appearance_description"] == "僧衣参考图外貌。"


def test_resolve_segment_image_refs_descriptor() -> None:
    descriptor = ResolveSegmentImageRefsNode().describe()

    assert descriptor.ref == "tool.resolve_segment_image_refs.v1"
    assert descriptor.kind == "tool"
    assert descriptor.input_schema["required"] == ["segment_assignments", "asset_catalog"]
    assert descriptor.output_schema["required"] == ["segment_assignments"]


async def test_resolve_segment_image_refs_preserves_presence_and_fills_appearance() -> None:
    node = ResolveSegmentImageRefsNode()

    result = await node.run(
        None,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [
                        {
                            "asset_type": "character",
                            "asset_name": "林冲",
                            "asset_tags": ["囚服", "毡笠"],
                            "presence": "present",
                            "image_ref": {"kind": "asset", "asset_id": "input-ref", "role": "reference"},
                        }
                    ],
                    "key_props": ["花枪"],
                }
            ],
            "asset_catalog": {
                "approved_assets": {
                    "characters": [
                        {
                            "asset_type": "character",
                            "asset_name": "林冲",
                            "asset_tags": ["囚服", "毡笠"],
                            "appearance_description": "戴毡笠、穿囚服。",
                            "asset_id": "catalog-ref",
                        }
                    ]
                }
            },
        },
    )

    character = result.output["segment_assignments"][0]["characters"][0]
    assert character["asset_tags"] == ["囚服", "毡笠"]
    assert character["appearance_description"] == "戴毡笠、穿囚服。"
    assert character["presence"] == "present"
    assert character["image_ref"] == {"kind": "asset", "asset_id": "input-ref", "role": "reference"}


def test_segment_storyboard_tool_descriptors() -> None:
    prepare_descriptor = PrepareSegmentStoryboardInputsNode().describe()
    merge_descriptor = MergeSegmentStoryboardDescriptionsNode().describe()
    panel_cards_descriptor = PrepareStoryboardPanelCardsNode().describe()
    review_descriptor = StoryboardReviewRefineNode(
        model_router=ChatModelRouter(),
        provider="deepseek",
        model="test-model",
    ).describe()

    assert prepare_descriptor.ref == "tool.prepare_segment_storyboard_inputs.v1"
    assert prepare_descriptor.kind == "tool"
    assert prepare_descriptor.input_schema["required"] == [
        "source_script",
        "segments",
        "segment_assignments",
    ]
    assert prepare_descriptor.input_schema["properties"]["storyboard_options"]["properties"] == {
        "no_material": {"type": "boolean"},
        "enrich_description": {"type": "boolean"},
        "prompts_per_item": {"type": "integer", "minimum": 1, "maximum": 6, "default": 1},
        "images_per_prompt": {"type": "integer", "minimum": 1, "maximum": 6, "default": 1},
    }
    assert prepare_descriptor.output_schema["properties"]["shared_context"]["properties"]["storyboard_options"][
        "properties"
    ] == {
        "no_material": {"type": "boolean"},
        "enrich_description": {"type": "boolean"},
        "prompts_per_item": {"type": "integer", "minimum": 1, "maximum": 6, "default": 1},
        "images_per_prompt": {"type": "integer", "minimum": 1, "maximum": 6, "default": 1},
    }
    assert prepare_descriptor.output_schema["properties"]["shared_context"]["properties"]["prompt_rules"]["required"] == [
        "material_rule",
        "enrich_rule",
        "material_thinking",
        "enrich_thinking",
    ]
    assert "all_segments" not in prepare_descriptor.output_schema["properties"]["shared_context"]["properties"]
    item_properties = prepare_descriptor.output_schema["properties"]["items"]["items"]["properties"]
    assert {
        "paragraph_text",
        "panel_count",
        "present_characters",
        "location",
        "key_props",
    }.issubset(item_properties)
    assert "current_segment" not in item_properties
    assert (
        "neighbor_segments"
        not in item_properties
    )
    assert merge_descriptor.ref == "tool.merge_segment_storyboard_descriptions.v1"
    assert merge_descriptor.kind == "tool"
    assert merge_descriptor.output_schema["required"] == ["segment_descriptions"]
    assert panel_cards_descriptor.ref == "tool.prepare_storyboard_panel_cards.v1"
    assert panel_cards_descriptor.kind == "tool"
    assert panel_cards_descriptor.output_schema["required"] == ["panel_cards"]
    assert review_descriptor.ref == "ai.storyboard_review_refine.v1"
    assert review_descriptor.kind == "ai"


async def test_merge_segment_storyboard_descriptions_keeps_failed_segments() -> None:
    node = MergeSegmentStoryboardDescriptionsNode()

    result = await node.run(
        None,
        {
            "results": [
                {
                    "index": 1,
                    "segment_title": "失败段",
                    "status": "failed",
                    "error": {"code": "structured_json_parse_failed", "message": "DeepSeek response is not valid JSON"},
                },
                {
                    "index": 0,
                    "segment_title": "成功段",
                    "image_prompt": "林冲踏雪前行。",
                },
            ]
        },
    )

    assert [item["index"] for item in result.output["segment_descriptions"]] == [0, 1]
    failed = result.output["segment_descriptions"][1]
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "structured_json_parse_failed"


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
                    "panel_plan": {"panel_count": 2, "panels": [{"description": "起"}, {"description": "承"}]},
                    "image_prompt": "单个大分格，低机位远中景。林冲背对镜头踏雪前行，鲁智深侧对镜头守在树后；野猪林雪地以前景树干遮挡、中景人物穿行、背景林木延伸形成斜向纵深，冷月光从画面右上方落下，风雪斜扫，花枪在人物身侧形成方向线。",
                }
            ],
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "location": "野猪林",
                    "location_asset": {
                        "asset_type": "scene",
                        "asset_name": "野猪林",
                        "image_ref": {"kind": "asset", "asset_id": "asset-boar-forest", "role": "reference"},
                    },
                    "characters": [
                        {
                            "asset_type": "character",
                            "asset_name": "林冲",
                            "asset_tags": ["囚服"],
                            "image_ref": {"kind": "asset", "asset_id": "asset-linchong", "role": "reference"},
                        },
                        {
                            "asset_type": "character",
                            "asset_name": "鲁智深",
                            "asset_tags": ["僧衣"],
                            "image_ref": {"kind": "asset", "asset_id": "asset-luzhishen", "role": "reference"},
                        }
                    ],
                    "key_props": ["花枪"],
                    "prop_assets": [
                        {
                            "asset_type": "prop",
                            "asset_name": "花枪",
                            "image_ref": {"kind": "asset", "asset_id": "asset-spear", "role": "reference"},
                        }
                    ],
                }
            ],
            "storyboard_items": [
                {
                    "index": 0,
                    "paragraph_text": "林冲踏雪。",
                    "panel_count": "1",
                    "present_characters": ["林冲", "鲁智深"],
                    "location": "野猪林",
                    "key_props": ["花枪"],
                }
            ],
            "shared_context": {
                "full_script": "完整剧本",
                "world_background": "水浒世界，北宋末年。",
                "storyboard_options": {"no_material": False, "enrich_description": False},
            },
            "generation_rules": "风格指令：参考《罗小黑战记》。",
            "negative_prompt": "low quality",
        },
    )

    card = result.output["panel_cards"][0]
    assert card["card_id"] == "segment-0"
    assert card["panel_count"] == "2"
    assert card["panel_plan"] == {"panel_count": 2, "panels": [{"description": "起"}, {"description": "承"}]}
    assert card["reference_images"] == [
        {
            "label": "林冲",
            "asset_type": "character",
            "asset_name": "林冲",
            "asset_tags": ["囚服"],
            "image_ref": {"kind": "asset", "asset_id": "asset-linchong", "role": "reference"},
            "reference_index": 1,
            "source": "asset",
        },
        {
            "label": "鲁智深",
            "asset_type": "character",
            "asset_name": "鲁智深",
            "asset_tags": ["僧衣"],
            "image_ref": {"kind": "asset", "asset_id": "asset-luzhishen", "role": "reference"},
            "reference_index": 2,
            "source": "asset",
        },
        {
            "label": "野猪林",
            "asset_type": "scene",
            "asset_name": "野猪林",
            "image_ref": {"kind": "asset", "asset_id": "asset-boar-forest", "role": "reference"},
            "reference_index": 3,
            "source": "asset",
        },
        {
            "label": "花枪",
            "asset_type": "prop",
            "asset_name": "花枪",
            "image_ref": {"kind": "asset", "asset_id": "asset-spear", "role": "reference"},
            "reference_index": 4,
            "source": "asset",
        },
    ]
    assert card["prompt"].startswith("画风：\n参考《罗小黑战记》。")
    assert "参考图：\n图1是角色林冲\n图2是角色鲁智深\n图3是场景野猪林\n图4是道具花枪" in card["prompt"]
    assert "画面：\n单个大分格" in card["prompt"]
    assert card["prompt"].endswith("Negative Prompt： low quality")
    assert card["prompt"].index("画风：") < card["prompt"].index("参考图：")
    assert card["prompt"].index("参考图：") < card["prompt"].index("画面：")
    assert card["prompt"].index("画面：") < card["prompt"].index("Negative Prompt：")
    assert "林冲（参考图1）背对镜头踏雪前行" in card["prompt"]
    assert "鲁智深（参考图2）侧对镜头守在树后" in card["prompt"]
    assert "画面内容提示词" not in card["prompt"]
    assert "## 画面内容" not in card["prompt"]
    assert "## 画面风格关键词" not in card["prompt"]
    assert "低机位远中景" in card["prompt"]
    assert "形成斜向纵深" in card["prompt"]
    assert "style" not in card
    assert "constraints" not in card
    assert "额外约束" not in card["prompt"]
    assert "补充生成规则" not in card["prompt"]
    assert "固定图像生成规则" not in card["prompt"]
    assert "在场资产约束" not in card["prompt"]
    assert "画幅比例" not in card["prompt"]
    assert "输出清晰度" not in card["prompt"]
    assert "出场角色：林冲（囚服）、鲁智深（僧衣）" not in card["prompt"]
    assert card["generation_config"] == {"prompts_per_item": 1, "images_per_prompt": 1}
    assert card["visible_characters"] == ["林冲", "鲁智深"]
    assert card["status"] == "ready"
    assert card["error"] == ""


async def test_prepare_storyboard_panel_cards_groups_prompt_variants_in_one_card() -> None:
    node = PrepareStoryboardPanelCardsNode()

    result = await node.run(
        None,
        {
            "segment_descriptions": [
                {
                    "index": 0,
                    "prompt_variant_index": 0,
                    "prompt_variant_count": 2,
                    "segment_title": "机密房商议",
                    "panel_plan": {"panel_count": 2, "panels": [{"description": "起"}, {"description": "承"}]},
                    "image_prompt": "两格横向布局，众公差围桌商议。",
                },
                {
                    "index": 0,
                    "prompt_variant_index": 1,
                    "prompt_variant_count": 2,
                    "segment_title": "机密房商议",
                    "panel_plan": {"panel_count": 4, "panels": [{"description": "起"}]},
                    "image_prompt": "四格错落布局，何涛从旁观察众人。",
                },
            ],
            "segment_assignments": [{"segment_index": 0, "characters": [], "key_props": []}],
            "storyboard_items": [
                {
                    "index": 0,
                    "prompt_variant_index": 0,
                    "prompt_variant_count": 2,
                    "paragraph_text": "机密房商议。",
                    "panel_count": "auto",
                },
                {
                    "index": 0,
                    "prompt_variant_index": 1,
                    "prompt_variant_count": 2,
                    "paragraph_text": "机密房商议。",
                    "panel_count": "auto",
                },
            ],
            "generation_rules": "风格指令：参考《罗小黑战记》。",
            "negative_prompt": "low quality",
            "prompts_per_item": 2,
            "images_per_prompt": 2,
        },
    )

    cards = result.output["panel_cards"]
    assert len(cards) == 1
    card = cards[0]
    assert card["card_id"] == "segment-0"
    assert card["panel_index"] == 0
    assert card["prompt_variant_index"] == 0
    assert card["prompt_variant_label"] == "候选 1/2"
    assert card["panel_count"] == "2"
    assert card["panel_count_variants"] == ["2", "4"]
    assert len(card["prompt_variants"]) == 2
    assert "两格横向布局" in card["prompt_variants"][0]
    assert "四格错落布局" in card["prompt_variants"][1]
    assert card["panel_plan_variants"] == [
        {"panel_count": 2, "panels": [{"description": "起"}, {"description": "承"}]},
        {"panel_count": 4, "panels": [{"description": "起"}]},
    ]
    assert card["source_item"]["prompt_variant_index"] == 0
    assert card["generation_config"] == {"prompts_per_item": 2, "images_per_prompt": 2}


async def test_prepare_storyboard_panel_cards_marks_failed_segments() -> None:
    node = PrepareStoryboardPanelCardsNode()

    result = await node.run(
        None,
        {
            "segment_descriptions": [
                {
                    "index": 1,
                    "segment_title": "失败段",
                    "status": "failed",
                    "error": {
                        "code": "structured_json_parse_failed",
                        "message": "DeepSeek response is not valid JSON",
                    },
                }
            ],
            "segment_assignments": [{"segment_index": 1, "characters": [], "key_props": []}],
            "generation_rules": "风格指令。",
        },
    )

    card = result.output["panel_cards"][0]
    assert card["card_id"] == "segment-1"
    assert card["status"] == "failed"
    assert card["error"] == "DeepSeek response is not valid JSON（structured_json_parse_failed）"
    assert "当前段落画面提示词生成失败" in card["prompt"]


async def test_prepare_storyboard_panel_cards_marks_numbered_group_characters() -> None:
    node = PrepareStoryboardPanelCardsNode()

    result = await node.run(
        None,
        {
            "segment_descriptions": [
                {
                    "index": 0,
                    "segment_title": "登船",
                    "thinking": "大规模行动。",
                    "image_prompt": "官兵1背对镜头登船，官兵2侧对镜头回望，何涛面对镜头指挥。",
                }
            ],
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [
                        {
                            "asset_type": "character",
                            "asset_name": "何涛",
                            "image_ref": {"kind": "asset", "asset_id": "asset-hetao", "role": "reference"},
                        },
                        {
                            "asset_type": "character",
                            "asset_name": "捕盗巡检",
                            "image_ref": {"kind": "asset", "asset_id": "asset-xunjian", "role": "reference"},
                        },
                        {
                            "asset_type": "character",
                            "asset_name": "官兵",
                            "image_ref": {"kind": "asset", "asset_id": "asset-guanbing", "role": "reference"},
                        },
                    ],
                    "key_props": [],
                }
            ],
        },
    )

    card = result.output["panel_cards"][0]
    assert "图1是角色何涛" in card["prompt"]
    assert "图2是角色捕盗巡检" in card["prompt"]
    assert "图3是角色官兵" in card["prompt"]
    assert "官兵（参考图3）1背对镜头登船" in card["prompt"]
    assert "官兵（参考图3）2侧对镜头回望" in card["prompt"]
    assert "何涛（参考图1）面对镜头指挥" in card["prompt"]


async def test_prepare_storyboard_panel_cards_does_not_mark_character_inside_location_phrase() -> None:
    node = PrepareStoryboardPanelCardsNode()

    result = await node.run(
        None,
        {
            "segment_descriptions": [
                {
                    "index": 0,
                    "segment_title": "庄院议事",
                    "thinking": "室内议事。",
                    "image_prompt": "画面：石碣村阮小五庄院内，粗木梁下，阮小五居中，吴用侧对镜头。",
                }
            ],
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [
                        {
                            "asset_type": "character",
                            "asset_name": "阮小五",
                            "image_ref": {"kind": "asset", "asset_id": "asset-ruan5", "role": "reference"},
                        },
                        {
                            "asset_type": "character",
                            "asset_name": "吴用",
                            "image_ref": {"kind": "asset", "asset_id": "asset-wuyong", "role": "reference"},
                        },
                    ],
                    "key_props": [],
                }
            ],
        },
    )

    prompt = result.output["panel_cards"][0]["prompt"]
    assert "石碣村阮小五庄院内" in prompt
    assert "石碣村阮小五（参考图1）庄院内" not in prompt
    assert "阮小五（参考图1）居中" in prompt
    assert "吴用（参考图2）侧对镜头" in prompt


async def test_resolve_accessory_asset_refs_uses_match_or_first_variant_asset() -> None:
    node = ResolveAccessoryAssetRefsNode()

    result = await node.run(
        None,
        {
            "characters": [
                {
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服"],
                    "existing_variants": [
                        {
                            "asset_id": "variant-prisoner-base",
                            "name": "林冲_囚服",
                            "asset_tags": ["囚服"],
                            "storage_uri": "https://cdn.test/prisoner-base.png",
                            "appearance_description": "囚服基础参考图。",
                            "tags": ["角色", "林冲", "囚服"],
                        },
                        {
                            "asset_id": "variant-prisoner-hat",
                            "name": "林冲_囚服_毡笠",
                            "asset_tags": ["囚服", "毡笠"],
                            "storage_uri": "https://cdn.test/prisoner-hat.png",
                            "appearance_description": "囚服加毡笠参考图。",
                            "tags": ["角色", "林冲", "囚服", "毡笠"],
                        },
                    ],
                },
            ],
            "variant_results": [
                {
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服"],
                    "matched_asset_id": "variant-prisoner-base",
                }
            ],
            "accessory_results": [
                {
                    "asset_type": "character",
                    "asset_name": "林冲",
                    "asset_tags": ["囚服", "毡笠", "披风"],
                    "existing_asset_tags": ["毡笠"],
                    "new_asset_tags": ["披风"],
                    "has_new_asset_tags": True,
                    "reason": "毡笠已存在，披风未命中。",
                }
            ],
        },
    )

    selected = result.output["results"][0]["selected_accessory_assets"]
    assert selected == [
        {
            "asset_tag": "毡笠",
            "matched": True,
            "asset_id": "variant-prisoner-hat",
            "asset_name": "林冲_囚服_毡笠",
            "asset_tags": ["囚服", "毡笠"],
            "asset_ref": {"kind": "asset", "asset_id": "variant-prisoner-hat", "role": "reference"},
            "storage_uri": "https://cdn.test/prisoner-hat.png",
            "appearance_description": "囚服加毡笠参考图。",
            "source": "matched_asset_tag",
        },
        {
            "asset_tag": "披风",
            "matched": False,
            "asset_id": "variant-prisoner-base",
            "asset_name": "林冲_囚服",
            "asset_tags": ["囚服"],
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
            "asset_catalog": {"characters": [{"asset_type": "character", "asset_name": "宋江"}], "assets": [], "props": []},
            "asset_images": [{"asset_type": "character", "asset_name": "宋江", "asset_id": "asset-songjiang"}],
            "prompt_results": [],
            "generation_summary": {
                "total_asset_count": 1,
                "new_asset_count": 0,
                "matched_asset_count": 1,
                "has_assets_to_generate": False,
            },
        },
    )
    loaded = await EpisodeMetadataFromAssetNode().run(
        ctx,
        {"episode_asset_id": result.output["episode_asset_id"], "no_material": True, "enrich_description": True},
    )

    assert service.created["asset-episode"].metadata["type"] == "episode_metadata"
    assert "tags" not in service.created["asset-episode"].metadata
    assert loaded.output["episode_name"] == "23、私放晁天王"
    assert loaded.output["source_script"] == "宋江见了晁盖。"
    assert loaded.output["storyboard_options"] == {
        "no_material": True,
        "enrich_description": True,
        "prompts_per_item": 1,
        "images_per_prompt": 1,
    }
    assert result.output["asset_images"] == [
        {"asset_type": "character", "asset_name": "宋江", "asset_id": "asset-songjiang"}
    ]
    assert result.output["generation_summary"] == {
        "total_asset_count": 1,
        "new_asset_count": 0,
        "matched_asset_count": 1,
        "has_assets_to_generate": False,
    }
    assert loaded.output["generation_summary"] == result.output["generation_summary"]
    assert loaded.output["asset_catalog"]["generation_summary"] == result.output["generation_summary"]
    assert loaded.output["asset_catalog"]["approved_assets"]["characters"][0]["asset_name"] == "宋江"
    assert loaded.asset_refs[0].asset_id == "asset-episode"

    storyboard_ctx = NodeContext(
        user_id="user-1",
        project_id="project-1",
        task_id="task-1",
        node_id="select_episode_metadata",
        node_execution_id="exec-2",
        config={},
        output_schema={
            "type": "object",
            "required": ["episode_name", "episode_summary", "source_script", "asset_catalog", "episode_asset_id"],
            "properties": {
                "episode_name": {"type": "string", "minLength": 1},
                "episode_summary": {"type": "string"},
                "source_script": {"type": "string", "minLength": 1},
                "background": {"type": "string"},
                "asset_catalog": {"type": "object", "additionalProperties": True},
                "asset_images": {"type": "array", "items": {"type": "object"}},
                "episode_asset_id": {"type": "string", "minLength": 1},
                "storyboard_options": {
                    "type": "object",
                    "properties": {
                        "no_material": {"type": "boolean"},
                        "enrich_description": {"type": "boolean"},
                        "prompts_per_item": {"type": "integer", "minimum": 1, "maximum": 6, "default": 1},
                        "images_per_prompt": {"type": "integer", "minimum": 1, "maximum": 6, "default": 1},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
        asset_service=service,  # type: ignore[arg-type]
        event_sink=None,
        logger=None,
    )
    storyboard_loaded = await EpisodeMetadataFromAssetNode().run(
        storyboard_ctx,
        {"episode_asset_id": result.output["episode_asset_id"]},
    )
    assert "generation_summary" not in storyboard_loaded.output
    assert storyboard_loaded.output["asset_catalog"]["generation_summary"] == result.output["generation_summary"]


async def test_prepare_storyboard_asset_index_keeps_only_lightweight_identity_fields() -> None:
    result = await PrepareStoryboardAssetIndexNode().run(
        None,
        {
            "asset_catalog": {
                "approved_assets": {
                    "characters": [
                        {
                            "asset_name": "何涛",
                            "asset_type": "character",
                            "aliases": ["何观察"],
                            "summary": "官府观察。",
                            "prompt": "很长的生成提示词",
                            "reference_image_ref": {"kind": "asset", "asset_id": "asset-hetiao"},
                        }
                    ],
                    "assets": [{"asset_name": "机密房", "asset_type": "scene", "description": "官府内议事处。"}],
                    "props": [{"asset_name": "钢叉", "asset_type": "prop"}],
                }
            }
        },
    )

    assert result.output == {
        "asset_index": {
            "characters": [
                {
                    "asset_name": "何涛",
                    "asset_type": "character",
                    "aliases": ["何观察"],
                    "summary": "官府观察。",
                }
            ],
            "locations": [{"asset_name": "机密房", "asset_type": "scene", "description": "官府内议事处。"}],
            "props": [{"asset_name": "钢叉", "asset_type": "prop"}],
        }
    }
    assert "prompt" not in str(result.output)
    assert "reference_image_ref" not in str(result.output)


async def test_complete_asset_images_prepares_only_missing_prompts() -> None:
    node = CompleteAssetImagesNode()

    result = await node.run(
        None,
        {
            "decision": "generate_missing",
            "prompt_results": [
                {"asset_type": "character", "asset_name": "林冲", "prompt": "生成林冲", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
                {"asset_type": "character", "asset_name": "鲁智深", "prompt": "生成鲁智深", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
            ],
            "manual_images": ["https://cdn.test/linchong.png"],
        },
    )

    assert result.output["next_action"] == "generate_missing"
    assert result.output["missing_count"] == 1
    assert result.output["asset_images"] == [
        {
            "asset_type": "character",
            "asset_name": "林冲",
            "image_url": "https://cdn.test/linchong.png",
            "source": "manual_upload",
        }
    ]
    assert result.output["missing_prompt_results"] == [
        {"asset_type": "character", "asset_name": "鲁智深", "prompt": "生成鲁智深", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}}
    ]


async def test_complete_asset_images_matches_uploaded_cards_by_asset_identity() -> None:
    node = CompleteAssetImagesNode()

    result = await node.run(
        None,
        {
            "decision": "generate_missing",
            "prompt_results": [
                {"asset_type": "character", "asset_name": "林冲", "prompt": "生成林冲", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
                {"asset_type": "character", "asset_name": "鲁智深", "prompt": "生成鲁智深", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
            ],
            "manual_images": [
                {
                        "asset_type": "character",
                        "asset_name": "鲁智深",
                    "image_url": "https://cdn.test/luzhishen.png",
                    "source": "manual_upload",
                }
            ],
        },
    )

    assert result.output["next_action"] == "generate_missing"
    assert result.output["missing_count"] == 1
    assert result.output["missing_prompt_results"] == [
        {"asset_type": "character", "asset_name": "林冲", "prompt": "生成林冲", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}}
    ]


async def test_complete_asset_images_matches_uploaded_cards_by_prop_identity() -> None:
    node = CompleteAssetImagesNode()

    result = await node.run(
        None,
        {
            "decision": "generate_missing",
            "prompt_results": [
                {"asset_type": "prop", "asset_name": "花枪", "prompt": "生成花枪", "reference_image_ref": {"kind": "asset", "asset_id": "prop-ref", "role": "reference"}},
            ],
            "manual_images": [
                {
                    "asset_type": "prop",
                    "asset_name": "花枪",
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
            "target_asset_name": "鲁智深",
            "prompt_results": [
                {"asset_type": "character", "asset_name": "林冲", "prompt": "生成林冲", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
                {"asset_type": "character", "asset_name": "鲁智深", "asset_tags": ["僧衣"], "prompt": "生成鲁智深僧衣", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
                {"asset_type": "prop", "asset_name": "水火棍", "prompt": "生成水火棍", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}},
            ],
            "manual_images": [
                {
                        "asset_type": "character",
                        "asset_name": "林冲",
                    "image_url": "https://cdn.test/linchong.png",
                    "source": "manual_upload",
                }
            ],
        },
    )

    assert result.output["next_action"] == "generate_missing"
    assert result.output["missing_count"] == 1
    assert result.output["missing_prompt_results"] == [
        {"asset_type": "character", "asset_name": "鲁智深", "asset_tags": ["僧衣"], "prompt": "生成鲁智深僧衣", "reference_image_ref": {"kind": "asset", "asset_id": "template", "role": "reference"}}
    ]


async def test_enrich_characters_carries_matched_asset_ref() -> None:
    node = EnrichCharactersNode()

    result = await node.run(
        None,
        {
            "characters": [{"asset_type": "prop", "asset_name": "花枪", "description": "林冲使用的长枪"}],
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


async def test_enrich_characters_matches_existing_asset_by_identity_name() -> None:
    node = EnrichCharactersNode()

    result = await node.run(
        None,
        {
            "characters": [
                {
                    "asset_type": "character",
                    "asset_name": "众公差",
                    "asset_tags": ["公差皂衣"],
                    "appearance_description": "穿皂衣的押解公差。",
                }
            ],
            "matched_by_name": [],
            "existing_assets": [
                {
                    "asset_id": "asset_court_runner",
                    "name": "角色_众公差_公差皂衣",
                    "metadata": {
                        "public_url": "https://cdn.test/court-runner.png",
                        "appearance_description": "一名穿皂衣、戴公差帽的押解公差。",
                    },
                }
            ],
        },
    )

    character = result.output["characters"][0]
    assert character["matched"] is True
    assert character["matched_asset_id"] == "asset_court_runner"
    assert character["matched_asset_name"] == "角色_众公差_公差皂衣"
    assert character["matched_asset_ref"] == {
        "kind": "asset",
        "asset_id": "asset_court_runner",
        "role": "reference",
    }
    assert character["reference_appearance_description"] == "一名穿皂衣、戴公差帽的押解公差。"


async def test_enrich_characters_matches_character_tags_without_order() -> None:
    node = EnrichCharactersNode()

    result = await node.run(
        None,
        {
            "characters": [
                {
                    "asset_type": "character",
                    "asset_name": "何涛",
                    "asset_tags": ["佩刀", "官帽"],
                    "appearance_description": "佩刀官员。",
                }
            ],
            "matched_by_name": [],
            "existing_assets": [
                {
                    "asset_id": "asset_hetao",
                    "name": "角色_何涛_官兵装束_官帽、佩刀、革带",
                    "tags": ["角色", "官帽、佩刀、革带", "何涛", "官兵装束"],
                    "metadata": {"public_url": "https://cdn.test/hetao.png"},
                }
            ],
        },
    )

    character = result.output["characters"][0]
    assert character["matched"] is True
    assert character["matched_asset_id"] == "asset_hetao"
    assert character["matched_asset_name"] == "角色_何涛_官兵装束_官帽、佩刀、革带"


async def test_enrich_characters_matches_scene_name_with_existing_scene_asset() -> None:
    node = EnrichCharactersNode()

    result = await node.run(
        None,
        {
            "characters": [
                {
                    "name": "山神庙外",
                    "description": "风雪夜里的破败庙外空地。",
                    "time_of_day": "夜晚",
                    "location_type": "户外",
                }
            ],
            "matched_by_name": [],
            "existing_assets": [
                {
                    "asset_id": "asset_scene_temple",
                    "name": "地点_山神庙外",
                    "metadata": {
                        "public_url": "https://cdn.test/temple-yard.png",
                        "appearance_description": "风雪夜色中的山神庙外景。",
                    },
                }
            ],
        },
    )

    scene = result.output["characters"][0]
    assert scene["asset_type"] == "scene"
    assert scene["asset_name"] == "山神庙外"
    assert scene["matched"] is True
    assert scene["matched_asset_id"] == "asset_scene_temple"
    assert scene["matched_asset_name"] == "地点_山神庙外"


async def test_enrich_characters_matches_prop_identity_with_existing_prop_asset() -> None:
    node = EnrichCharactersNode()

    result = await node.run(
        None,
        {
            "characters": [
                {
                    "asset_type": "prop",
                    "asset_name": "花枪",
                    "description": "红缨长枪。",
                    "category": "武器",
                }
            ],
            "matched_by_name": [],
            "existing_assets": [
                {
                    "asset_id": "asset_prop_spear",
                    "name": "道具_花枪",
                    "metadata": {"public_url": "https://cdn.test/spear.png"},
                }
            ],
        },
    )

    prop = result.output["characters"][0]
    assert prop["asset_type"] == "prop"
    assert prop["asset_name"] == "花枪"
    assert prop["matched"] is True
    assert prop["matched_asset_id"] == "asset_prop_spear"
    assert prop["matched_asset_name"] == "道具_花枪"


async def test_enrich_characters_matches_tagless_prop_by_typed_name() -> None:
    node = EnrichCharactersNode()

    result = await node.run(
        None,
        {
            "characters": [
                {
                    "asset_type": "prop",
                    "asset_name": "钢叉",
                    "description": "铁制三股钢叉。",
                    "category": "武器",
                }
            ],
            "matched_by_name": [],
            "existing_assets": [
                {
                    "asset_id": "asset_prop_fork",
                    "name": "道具_钢叉_武器_公差",
                    "tags": ["道具", "公差", "钢叉", "武器"],
                    "metadata": {"public_url": "https://cdn.test/fork.png"},
                }
            ],
        },
    )

    prop = result.output["characters"][0]
    assert prop["matched"] is True
    assert prop["matched_asset_id"] == "asset_prop_fork"
    assert prop["matched_asset_name"] == "道具_钢叉_武器_公差"


async def test_enrich_characters_uses_scene_semantic_match_result() -> None:
    node = EnrichCharactersNode()

    result = await node.run(
        None,
        {
            "characters": [
                {
                    "asset_type": "scene",
                    "asset_name": "石碣村湖荡芦苇",
                    "asset_tags": ["湖泊", "芦苇荡", "户外"],
                    "description": "石碣村外水道纵横的湖荡芦苇战场。",
                }
            ],
            "matched_by_name": [],
            "semantic_matches": [
                {
                    "asset_type": "scene",
                    "asset_name": "石碣村湖荡芦苇",
                    "matched": True,
                    "matched_asset_id": "asset_scene_reeds",
                    "matched_asset_name": "地点_石碣村湖荡芦苇荡",
                    "reason": "两者都指石碣村外湖荡和芦苇荡水域，是同一地点资产。",
                }
            ],
        },
    )

    scene = result.output["characters"][0]
    assert scene["matched"] is True
    assert scene["matched_asset_id"] == "asset_scene_reeds"
    assert scene["matched_asset_name"] == "地点_石碣村湖荡芦苇荡"
    assert scene["matched_asset_ref"] == {
        "kind": "asset",
        "asset_id": "asset_scene_reeds",
        "role": "reference",
    }


async def test_prepare_asset_semantic_match_keeps_only_identity_and_description() -> None:
    node = PrepareAssetSemanticMatchNode()

    result = await node.run(
        None,
        {
            "default_asset_type": "scene",
            "items": [
                {
                    "asset_type": "scene",
                    "asset_name": "石碣村湖荡芦苇",
                    "asset_tags": ["湖泊", "芦苇荡"],
                    "description": "石碣村外水道纵横的湖荡芦苇战场。",
                    "storage_uri": "should-not-pass",
                }
            ],
            "candidates": [
                {
                    "asset_id": "asset_scene_reeds",
                    "name": "地点_石碣村湖荡芦苇荡",
                    "tags": ["地点", "石碣村湖荡芦苇荡"],
                    "metadata": {
                        "prompt": "广袤水域，港汊纵横，高过人的黄绿色芦苇丛密布。",
                        "public_url": "should-not-pass",
                    },
                    "storage_uri": "should-not-pass",
                }
            ],
        },
    )

    assert result.output == {
        "items": [
            {
                "asset_type": "scene",
                "asset_name": "石碣村湖荡芦苇",
                "asset_tags": ["湖泊", "芦苇荡"],
                "description": "石碣村外水道纵横的湖荡芦苇战场。",
            }
        ],
        "candidates": [
            {
                "asset_id": "asset_scene_reeds",
                "asset_type": "scene",
                "asset_name": "石碣村湖荡芦苇荡",
                "asset_tags": [],
                "description": "广袤水域，港汊纵横，高过人的黄绿色芦苇丛密布。",
            }
        ],
    }


async def test_complete_asset_images_merges_manual_and_generated_images() -> None:
    node = CompleteAssetImagesNode()

    result = await node.run(
        None,
        {
            "decision": "finish",
            "manual_images": [
                {"asset_type": "character", "asset_name": "林冲", "image_url": "https://cdn.test/linchong.png", "source": "manual_upload"}
            ],
            "auto_images": [
                {"asset_type": "character", "asset_name": "鲁智深", "image_url": "https://cdn.test/luzhishen.png", "source": "ai_generated"}
            ],
        },
    )

    assert result.output["next_action"] == "finish"
    assert result.output["missing_count"] == 0
    assert result.output["asset_images"] == [
        {"asset_type": "character", "asset_name": "林冲", "image_url": "https://cdn.test/linchong.png", "source": "manual_upload"},
        {"asset_type": "character", "asset_name": "鲁智深", "image_url": "https://cdn.test/luzhishen.png", "source": "ai_generated"},
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
