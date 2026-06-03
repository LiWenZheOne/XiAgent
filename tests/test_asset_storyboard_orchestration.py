from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from xiagent.core.errors import ValidationError
from xiagent.core.schemas import validate_json_value
from xiagent.nodes import build_node_registry
from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.validator import validate_workflow_contract

ORCHESTRATION_WORKFLOW_PATH = Path(
    "workflows/global/asset_storyboard_generation.workflow.yaml"
)


def _nodes_by_id(contract: dict[str, Any]) -> dict[str, Any]:
    return {node["id"]: node for node in contract["nodes"]}


def _select_episode_outputs(contract: dict[str, Any]) -> dict[str, Any]:
    return _nodes_by_id(contract)["select_episode_metadata"]["outputs"]


def _select_episode_inputs(contract: dict[str, Any]) -> dict[str, Any]:
    return _nodes_by_id(contract)["select_episode_metadata"]["inputs"]


def _success_item_schema(node: dict[str, Any]) -> dict[str, Any]:
    item_schema = node["outputs"]["properties"]["results"]["items"]
    variants = item_schema.get("oneOf")
    if not variants:
        return item_schema
    for variant in variants:
        required = variant.get("required", [])
        if "status" not in required:
            return variant
    raise AssertionError("success item schema not found")


def _storyboard_segment_value(*, include_image_prompt: bool = False) -> dict[str, Any]:
    value: dict[str, Any] = {
        "index": 0,
        "segment_title": "雪夜",
        "paragraph_text": "林冲踏雪而行。",
        "panel_count": "1",
        "present_characters": ["林冲"],
        "location": "野猪林",
        "key_props": [],
        "segment_assignment": {},
        "scene_layout": {
            "location_summary": "野猪林雪地",
            "spatial_zones": ["前景树干", "中景雪路", "背景密林"],
            "character_positions": [{"name": "林冲", "position": "中景雪路"}],
            "prop_positions": [],
            "light_sources": ["右上方冷月光"],
            "layout_constraints": ["林冲始终沿雪路前行"],
        },
        "panel_plan": {
            "panel_count": 1,
            "page_layout": "单个大分格",
            "reading_order": "单格阅读",
            "panels": [
                {
                    "panel_number": 1,
                    "narrative_function": "建立雪夜压迫",
                    "visible_characters": ["林冲"],
                    "visible_props": [],
                    "shot_size": "远中景",
                    "camera_angle": "低机位仰视",
                    "camera_position": "雪路前方偏侧",
                    "composition": "前景树干遮挡，中景人物前行",
                    "action_moment": "踏雪前行",
                    "spatial_relationship": "人物位于中景，密林向背景延伸",
                    "transition_to_next": "以风雪方向承接",
                }
            ],
        },
        "thinking": "承接风雪氛围。",
        "think": "完整推理过程。",
    }
    if include_image_prompt:
        value.update(
            {
                "image_prompt": "单个大分格，低机位远中景。林冲背对镜头在雪中行走，前景树干遮挡，中景雪路通向背景密林；右上方冷月光压低明暗层次，风雪斜扫形成运动张力。",
                "review": {"passed": True, "rounds": 1, "issues": [], "revision_summary": "通过"},
                "review_history": [
                    {
                        "round": 1,
                        "passed": True,
                        "issues": [],
                        "revision_instructions": "",
                        "revision_summary": "通过",
                    }
                ],
                "prompt_review": {"passed": True, "rounds": 1, "issues": [], "revision_summary": "提示词通过"},
                "prompt_review_history": [
                    {
                        "round": 1,
                        "passed": True,
                        "issues": [],
                        "revision_instructions": "",
                        "revision_summary": "提示词通过",
                    }
                ],
            }
        )
    return value


def test_orchestration_workflow_contract_structure(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    assert contract["workflow"]["id"] == "asset_storyboard_generation"
    assert contract["workflow"]["version"] == "1.1.0"
    assert contract["workflow"]["scope"] == "global"
    assert contract["workflow"]["name"] == "分镜生成"

    select_outputs = _select_episode_outputs(contract)
    assert select_outputs["required"] == [
        "episode_name",
        "episode_summary",
        "source_script",
        "asset_catalog",
        "episode_asset_id",
    ]
    assert "storyboard_target" not in select_outputs["required"]
    assert "storyboard_target" not in select_outputs["properties"]
    assert "generation_summary" not in select_outputs["properties"]

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_orchestration_workflow_node_list(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    nodes_by_id = _nodes_by_id(contract)
    assert list(nodes_by_id) == [
        "select_episode_metadata",
        "split_script",
        "prepare_storyboard_asset_index",
        "assign_assets_to_segments",
        "resolve_segment_image_refs",
        "prepare_segment_storyboard_inputs",
        "analyze_scene_layout",
        "plan_storyboard_panels",
        "review_and_refine_storyboard_plan",
        "convert_storyboard_plan_to_image_prompt",
        "review_and_refine_image_prompt",
        "merge_segment_descriptions",
        "prepare_storyboard_panel_cards",
        "review_storyboard_image",
    ]
    assert {node_id: node["ref"] for node_id, node in nodes_by_id.items()} == {
        "select_episode_metadata": "tool.episode_metadata_from_asset.v1",
        "split_script": "tool.script_split.v1",
        "prepare_storyboard_asset_index": "tool.prepare_storyboard_asset_index.v1",
        "assign_assets_to_segments": "ai.deepseek_structured_json.v1",
        "resolve_segment_image_refs": "tool.resolve_segment_image_refs.v1",
        "prepare_segment_storyboard_inputs": "tool.prepare_segment_storyboard_inputs.v1",
        "analyze_scene_layout": "ai.parallel_deepseek_structured_json.v1",
        "plan_storyboard_panels": "ai.parallel_deepseek_structured_json.v1",
        "review_and_refine_storyboard_plan": "ai.storyboard_review_refine.v1",
        "convert_storyboard_plan_to_image_prompt": "ai.parallel_deepseek_structured_json.v1",
        "review_and_refine_image_prompt": "ai.storyboard_review_refine.v1",
        "merge_segment_descriptions": "tool.merge_segment_storyboard_descriptions.v1",
        "prepare_storyboard_panel_cards": "tool.prepare_storyboard_panel_cards.v1",
        "review_storyboard_image": "system.human_approval.v1",
    }

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_orchestration_workflow_edges_are_linear_dag(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    assert [edge for edge in contract["edges"] if "when" in edge] == []
    assert contract["edges"] == [
        {"from": "START", "to": "select_episode_metadata"},
        {"from": "select_episode_metadata", "to": "split_script"},
        {"from": "split_script", "to": "prepare_storyboard_asset_index"},
        {"from": "prepare_storyboard_asset_index", "to": "assign_assets_to_segments"},
        {"from": "assign_assets_to_segments", "to": "resolve_segment_image_refs"},
        {"from": "resolve_segment_image_refs", "to": "prepare_segment_storyboard_inputs"},
        {"from": "prepare_segment_storyboard_inputs", "to": "analyze_scene_layout"},
        {"from": "analyze_scene_layout", "to": "plan_storyboard_panels"},
        {"from": "plan_storyboard_panels", "to": "review_and_refine_storyboard_plan"},
        {"from": "review_and_refine_storyboard_plan", "to": "convert_storyboard_plan_to_image_prompt"},
        {"from": "convert_storyboard_plan_to_image_prompt", "to": "review_and_refine_image_prompt"},
        {"from": "review_and_refine_image_prompt", "to": "merge_segment_descriptions"},
        {"from": "merge_segment_descriptions", "to": "prepare_storyboard_panel_cards"},
        {"from": "prepare_storyboard_panel_cards", "to": "review_storyboard_image"},
        {"from": "review_storyboard_image", "to": "END"},
    ]

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_select_episode_node_loads_and_displays_episode_context(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    nodes_by_id = _nodes_by_id(contract)

    select_node = nodes_by_id["select_episode_metadata"]
    assert select_node["inputs"]["episode_asset_id"]["from_user"] is True
    assert select_node["inputs"]["no_material"]["from_user"] is True
    assert select_node["inputs"]["no_material"]["required"] is False
    assert select_node["inputs"]["enrich_description"]["from_user"] is True
    assert select_node["inputs"]["enrich_description"]["required"] is False
    select_ui = nodes_by_id["select_episode_metadata"]["ui"]["controls"]["input"]
    assert select_ui["options"]["fields"]["episode_asset_id"] == {
        "control_id": "ui.input.asset_picker.v1",
        "variant": "dropdown",
        "mode": "input",
        "asset_type": "text",
        "filter_tag_names": ["集元数据"],
        "placeholder": "请选择集信息资产",
        "preview_control_id": "ui.display.episode_context.v1",
    }
    select_sections = nodes_by_id["select_episode_metadata"]["ui"]["sections"]
    assert select_sections["input"]["wrapper"] is False
    assert select_sections["output"]["remove"] is True
    assert select_sections["events"]["visible"] is False
    assert "source_script" in select_node["outputs"]["required"]
    assert "asset_catalog" in select_node["outputs"]["required"]
    assert "generation_summary" not in select_node["outputs"]["properties"]
    assert select_node["outputs"]["properties"]["storyboard_options"]["properties"] == {
        "no_material": {"type": "boolean"},
        "enrich_description": {"type": "boolean"},
    }
    assert "output" not in select_node["ui"]["controls"]

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_episode_context_drives_segment_asset_assignment(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    nodes_by_id = _nodes_by_id(contract)

    split_node = nodes_by_id["split_script"]
    assert split_node["inputs"]["script"] == {
        "from": "$nodes.select_episode_metadata.output.source_script",
    }
    assert "background" not in split_node["inputs"]

    index_node = nodes_by_id["prepare_storyboard_asset_index"]
    assert index_node["inputs"] == {
        "asset_catalog": {
            "from": "$nodes.select_episode_metadata.output.asset_catalog",
        }
    }

    assign_node = nodes_by_id["assign_assets_to_segments"]
    prompt_vars = assign_node["inputs"]["prompt"]["vars"]
    assert prompt_vars["segments"] == {"from": "$nodes.split_script.output.segments"}
    assert prompt_vars["asset_index"] == {
        "from": "$nodes.prepare_storyboard_asset_index.output.asset_index",
    }
    assert prompt_vars["background"] == {
        "from": "$nodes.select_episode_metadata.output.background",
    }
    assert "不要输出 reason、visibility、asset_type、asset_tags、asset_id、image_ref 或 image_url" in assign_node["inputs"]["prompt"]["template"]
    assert "full_name" not in assign_node["inputs"]["prompt"]["template"]

    resolve_node = nodes_by_id["resolve_segment_image_refs"]
    assert resolve_node["inputs"] == {
        "segment_assignments": {
            "from": "$nodes.assign_assets_to_segments.output.segment_assignments",
        },
        "asset_catalog": {
            "from": "$nodes.select_episode_metadata.output.asset_catalog",
        },
    }

    prepare_node = nodes_by_id["prepare_segment_storyboard_inputs"]
    assert prepare_node["inputs"]["source_script"] == {
        "from": "$nodes.select_episode_metadata.output.source_script",
    }
    assert prepare_node["inputs"]["world_background"] == {
        "from": "$nodes.select_episode_metadata.output.background",
    }
    assert prepare_node["inputs"]["segments"] == {
        "from": "$nodes.split_script.output.segments",
    }
    assert prepare_node["inputs"]["segment_assignments"] == {
        "from": "$nodes.resolve_segment_image_refs.output.segment_assignments",
    }
    assert prepare_node["inputs"]["storyboard_options"] == {
        "from": "$nodes.select_episode_metadata.output.storyboard_options",
    }

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_select_episode_metadata_schema_collects_optional_storyboard_switches(
    test_settings,
) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    input_specs = _select_episode_inputs(contract)
    input_schema = input_specs["episode_asset_id"]["schema"]

    validate_json_value(input_schema, "asset_episode_001")
    validate_json_value(input_specs["no_material"]["schema"], True)
    validate_json_value(input_specs["enrich_description"]["schema"], False)
    assert input_specs["no_material"]["required"] is False
    assert input_specs["enrich_description"]["required"] is False
    assert "storyboard_target" not in _select_episode_outputs(contract)["properties"]

    with pytest.raises(ValidationError):
        validate_json_value(input_schema, "")

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_assign_assets_to_segments_output_schema(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    schema = _nodes_by_id(contract)["assign_assets_to_segments"]["outputs"]

    assert schema["type"] == "object"
    assert "segment_assignments" in schema["required"]
    validate_json_value(
        schema,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "characters": [
                        {
                            "asset_name": "林冲",
                            "presence": "present",
                        }
                    ],
                    "key_props": ["花枪", "旧毡笠"],
                }
            ]
        },
    )
    validate_json_value(
        schema,
        {"segment_assignments": [{"segment_index": 0, "characters": [], "key_props": []}]},
    )

    with pytest.raises(ValidationError):
        validate_json_value(
            schema,
            {"segment_assignments": [{"characters": [], "key_props": []}]},
        )

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_resolve_segment_image_refs_output_schema(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    schema = _nodes_by_id(contract)["resolve_segment_image_refs"]["outputs"]

    assert schema["type"] == "object"
    assert "segment_assignments" in schema["required"]
    validate_json_value(
        schema,
        {
            "segment_assignments": [
                {
                    "segment_index": 0,
                    "location": "野猪林",
                    "location_asset": {
                        "asset_type": "scene",
                        "asset_name": "野猪林",
                        "asset_tags": ["雪地"],
                        "image_ref": {
                            "kind": "asset",
                            "asset_id": "asset-boar-forest",
                            "role": "reference",
                        },
                        "image_url": "https://example.test/boar-forest.png",
                    },
                    "characters": [
                        {
                            "asset_type": "character",
                            "asset_name": "林冲",
                            "image_ref": {
                                "kind": "asset",
                                "asset_id": "asset-linchong",
                                "role": "reference",
                            },
                            "asset_tags": ["囚服雪地"],
                            "appearance_description": "戴毡笠、穿囚服。",
                            "presence": "present",
                        }
                    ],
                    "key_props": ["花枪"],
                    "prop_assets": [
                        {
                            "asset_type": "prop",
                            "asset_name": "花枪",
                            "image_ref": {
                                "kind": "asset",
                                "asset_id": "asset-spear",
                                "role": "reference",
                            },
                        }
                    ],
                }
            ]
        },
    )
    validate_json_value(
        schema,
        {
            "segment_assignments": [
                {"segment_index": 0, "characters": [{"asset_type": "character", "asset_name": "未知角色"}], "key_props": []}
            ]
        },
    )

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_prepare_segment_storyboard_inputs_output_schema(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    schema = _nodes_by_id(contract)["prepare_segment_storyboard_inputs"]["outputs"]

    assert schema["type"] == "object"
    assert "items" in schema["required"]
    validate_json_value(
        schema,
        {
            "items": [
                {
                    "index": 0,
                    "paragraph_text": "林冲踏雪而来。",
                    "panel_count": "1",
                    "present_characters": ["林冲"],
                    "location": "野猪林",
                    "scene_description": "雪地林道狭窄，两侧密林压迫，前景树干可遮挡视线。",
                    "key_props": [],
                    "segment_assignment": {
                        "segment_index": 0,
                        "characters": [
                            {
                                "asset_name": "林冲",
                                "asset_tags": ["囚服雪地"],
                                "appearance_description": "戴毡笠、穿囚服。",
                                "presence": "present",
                            }
                        ],
                        "key_props": [],
                    },
                }
            ],
            "shared_context": {
                "full_script": "完整剧本",
                "world_background": "水浒世界，北宋末年。",
                "storyboard_options": {"no_material": True, "enrich_description": True},
                "prompt_rules": {
                    "material_rule": "- 删除所有材质和质感审查，只保留空间、结构、色彩、光影、功能和动作信息。",
                    "enrich_rule": "- 额外落实遮挡物、空间深度和物理反馈。",
                    "material_thinking": "不讨论材质。",
                    "enrich_thinking": "逐项补充遮挡物。",
                },
            },
        },
    )

    with pytest.raises(ValidationError):
        validate_json_value(schema, {})

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_scene_layout_and_panel_plan_nodes_use_parallel_segment_items(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    nodes_by_id = _nodes_by_id(contract)
    layout_node = nodes_by_id["analyze_scene_layout"]
    plan_node = nodes_by_id["plan_storyboard_panels"]

    assert layout_node["ref"] == "ai.parallel_deepseek_structured_json.v1"
    assert layout_node["inputs"]["items"] == {
        "from": "$nodes.prepare_segment_storyboard_inputs.output.items",
    }
    assert layout_node["inputs"]["shared_context"] == {
        "from": "$nodes.prepare_segment_storyboard_inputs.output.shared_context",
    }
    assert "只分析当前段落的实际空间布局" in layout_node["inputs"]["system"]["value"]
    assert "{paragraph_text}" in layout_node["inputs"]["prompt_template"]["value"]
    assert "{world_background}" in layout_node["inputs"]["prompt_template"]["value"]
    assert "{full_script}" in layout_node["inputs"]["prompt_template"]["value"]
    assert "{material_rule}" in layout_node["inputs"]["prompt_template"]["value"]
    assert "{enrich_rule}" in layout_node["inputs"]["prompt_template"]["value"]
    assert layout_node["inputs"]["prompt_fields"]["value"] == [
        "index",
        "paragraph_text",
        "panel_count",
        "present_characters",
        "location",
        "scene_description",
        "key_props",
    ]
    prompt_template = layout_node["inputs"]["prompt_template"]["value"]
    assert "{scene_description}" in prompt_template
    assert "场景资产描述" in prompt_template
    assert "必须优先吸收其中的稳定空间结构" in prompt_template
    assert layout_node["inputs"]["continue_on_item_error"]["value"] is True
    layout_success_schema = _success_item_schema(layout_node)
    assert "scene_layout" in layout_success_schema["required"]
    assert "description" not in layout_success_schema["required"]

    validate_json_value(
        layout_node["outputs"],
        {
            "results": [
                {
                    "index": 0,
                    "paragraph_text": "林冲踏雪而行。",
                    "panel_count": "1",
                    "present_characters": ["林冲"],
                    "location": "野猪林",
                    "scene_description": "雪地林道狭窄，两侧密林压迫。",
                    "key_props": [],
                    "segment_assignment": {},
                    "scene_layout": {"location_summary": "野猪林雪地"},
                }
            ]
        },
    )
    validate_json_value(
        layout_node["outputs"],
        {
            "results": [
                {
                    "index": 1,
                    "paragraph_text": "鲁智深伏在林中。",
                    "panel_count": "1",
                    "present_characters": ["鲁智深"],
                    "location": "野猪林",
                    "key_props": [],
                    "segment_assignment": {},
                    "status": "failed",
                    "error": {"code": "structured_json_parse_failed", "message": "DeepSeek response is not valid JSON"},
                }
            ]
        },
    )

    assert plan_node["inputs"]["items"] == {"from": "$nodes.analyze_scene_layout.output.results"}
    assert "只基于当前段落和场景布局生成结构化分格计划" in plan_node["inputs"]["system"]["value"]
    assert "不写自然语言长描述" in plan_node["inputs"]["system"]["value"]
    assert "{world_background}" in plan_node["inputs"]["prompt_template"]["value"]
    assert "{full_script}" in plan_node["inputs"]["prompt_template"]["value"]
    plan_prompt = plan_node["inputs"]["prompt_template"]["value"]
    assert "分镜计划标准" in plan_prompt
    assert "panel_count 必须严格落实建议分格数" in plan_prompt
    assert "每格都必须有明确叙事功能和可见信息增量" in plan_prompt
    assert "每格必须明确入画角色、可见道具、动作瞬间、景别、机位、角度、构图、空间关系、光影氛围和与下一格的衔接" in plan_prompt
    assert "think：完整推理过程" in plan_prompt
    assert "目标 JSON 示例" in plan_prompt
    assert plan_node["inputs"]["required_input_fields"]["value"] == ["scene_layout"]
    plan_success_schema = _success_item_schema(plan_node)
    assert {"think", "segment_title", "panel_plan"}.issubset(set(plan_success_schema["required"]))
    assert "think" in plan_success_schema["properties"]
    assert plan_node["inputs"]["continue_on_item_error"]["value"] is True
    validate_json_value(
        plan_node["outputs"],
        {"results": [_storyboard_segment_value() | {"paragraph_text": "林冲踏雪而行。", "segment_assignment": {}}]},
    )
    validate_json_value(
        plan_node["outputs"],
        {
            "results": [
                {
                    "index": 1,
                    "paragraph_text": "鲁智深伏在林中。",
                    "panel_count": "1",
                    "present_characters": ["鲁智深"],
                    "location": "野猪林",
                    "key_props": [],
                    "segment_assignment": {},
                    "status": "failed",
                    "error": {"code": "structured_json_parse_failed", "message": "DeepSeek response is not valid JSON"},
                }
            ]
        },
    )

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_merge_segment_descriptions_output_schema(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    schema = _nodes_by_id(contract)["merge_segment_descriptions"]["outputs"]

    assert schema["type"] == "object"
    assert "segment_descriptions" in schema["required"]
    validate_json_value(
        schema,
        {"segment_descriptions": [_storyboard_segment_value(include_image_prompt=True)]},
    )
    validate_json_value(
        schema,
        {
            "segment_descriptions": [
                {
                    "index": 1,
                    "segment_title": "失败段",
                    "status": "failed",
                    "error": {"code": "structured_json_parse_failed", "message": "DeepSeek response is not valid JSON"},
                }
            ]
        },
    )

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_review_convert_and_prompt_review_nodes(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    nodes_by_id = _nodes_by_id(contract)
    review_node = nodes_by_id["review_and_refine_storyboard_plan"]
    convert_node = nodes_by_id["convert_storyboard_plan_to_image_prompt"]
    prompt_review_node = nodes_by_id["review_and_refine_image_prompt"]

    assert review_node["ref"] == "ai.storyboard_review_refine.v1"
    assert review_node["inputs"]["items"] == {
        "from": "$nodes.plan_storyboard_panels.output.results",
    }
    assert review_node["inputs"]["storyboard_items"] == {
        "from": "$nodes.prepare_segment_storyboard_inputs.output.items",
    }
    assert review_node["inputs"]["max_revision_rounds"]["value"] == 2
    assert review_node["inputs"]["review_output_field"]["value"] == "review"
    assert review_node["inputs"]["review_history_output_field"]["value"] == "review_history"
    assert review_node["inputs"]["continue_on_item_error"]["value"] is True
    plan_review_prompt = review_node["inputs"]["review_prompt_template"]["value"]
    plan_revision_prompt = review_node["inputs"]["revision_prompt_template"]["value"]
    assert "分镜计划标准" in plan_review_prompt
    assert "分镜计划标准" in plan_revision_prompt
    assert "只判断 scene_layout 和 panel_plan 是否符合分镜计划标准" in plan_review_prompt
    assert "不生成 image_prompt，不审查画面提示词写法" in plan_review_prompt
    assert "核心剧情动作是否被准确识别" in plan_review_prompt
    assert "页面排版是否形成清楚阅读节奏" in plan_review_prompt
    assert "入格剧情瞬间是否足以让因果关系成立" in plan_review_prompt
    assert "动作连续、视线引导、空间方向承接、情绪递进或反差切换" in plan_review_prompt
    assert "不写 image_prompt，不写自然语言长篇画面提示词" in plan_revision_prompt
    assert "输出中的 think 写完整推理过程" in plan_review_prompt
    assert "必须返回 think" in plan_revision_prompt
    assert "目标 JSON 示例" in plan_review_prompt
    assert "目标 JSON 示例" in plan_revision_prompt
    assert review_node["inputs"]["required_input_fields"]["value"] == ["scene_layout", "panel_plan"]
    review_success_schema = _success_item_schema(review_node)
    assert {"think", "scene_layout", "panel_plan", "review", "review_history"}.issubset(set(review_success_schema["required"]))
    assert "think" in review_success_schema["properties"]
    reviewed_value = _storyboard_segment_value()
    reviewed_value["review"] = {"passed": True, "rounds": 1, "issues": [], "revision_summary": "通过"}
    reviewed_value["review_history"] = [
        {
            "round": 1,
            "passed": True,
            "issues": [],
            "revision_instructions": "",
            "revision_summary": "通过",
        }
    ]
    validate_json_value(
        review_node["outputs"],
        {"results": [reviewed_value]},
    )
    validate_json_value(
        review_node["outputs"],
        {
            "results": [
                {
                    "index": 1,
                    "paragraph_text": "鲁智深伏在林中。",
                    "panel_count": "1",
                    "present_characters": ["鲁智深"],
                    "location": "野猪林",
                    "key_props": [],
                    "segment_assignment": {},
                    "status": "failed",
                    "error": {"code": "structured_json_parse_failed", "message": "DeepSeek response is not valid JSON"},
                }
            ]
        },
    )

    assert convert_node["ref"] == "ai.parallel_deepseek_structured_json.v1"
    assert convert_node["inputs"]["items"] == {"from": "$nodes.review_and_refine_storyboard_plan.output.results"}
    prompt = convert_node["inputs"]["prompt_template"]["value"]
    system = convert_node["inputs"]["system"]["value"]
    assert "忠于计划" in prompt
    assert "画面提示词标准" in prompt
    assert "think：完整推理过程" in prompt
    assert "先描述整体情节" in prompt
    assert "每格分别有哪些角色" in prompt
    assert "整页格子布局" in prompt
    assert "必须严格等于 panel_plan.panel_count" in prompt
    assert "如果 panel_plan 只有 1 格" in prompt
    assert "必须与 panel_plan.panels 一一对应" in prompt
    assert "禁止新增分格、删除分格、合并分格、拆分分格或重排分格" in prompt
    assert "前景/中景/背景各占画面大约多少" in prompt
    assert "主体位于画面左/右/中央或上下哪个区域" in prompt
    assert "角色面对镜头/背对镜头/侧对镜头或朝向哪里" in prompt
    assert "道具与人物、门窗、桌案、道路、林木等空间边界的相对位置" in prompt
    assert "不要使用 Markdown" in prompt
    assert "组装到“## 画面内容”" in prompt
    assert "不要拆成多字段对象" in prompt
    assert "目标 JSON 示例" in prompt
    assert convert_node["inputs"]["required_input_fields"]["value"] == ["scene_layout", "panel_plan"]
    convert_success_schema = _success_item_schema(convert_node)
    assert {"think", "image_prompt"}.issubset(set(convert_success_schema["required"]))
    assert "think" in convert_success_schema["properties"]
    assert "沿链路重新生成完整分段" in system
    assert "不得生成画风" in system
    assert "质量词" in system
    assert "参考图规则" in system
    assert convert_node["inputs"]["passthrough_fields"]["value"] == [
        "index",
        "segment_title",
        "paragraph_text",
        "panel_count",
        "present_characters",
        "location",
        "scene_description",
        "key_props",
        "segment_assignment",
        "scene_layout",
        "panel_plan",
        "review",
        "review_history",
    ]
    assert convert_node["inputs"]["continue_on_item_error"]["value"] is True
    validate_json_value(
        convert_node["outputs"],
        {"results": [_storyboard_segment_value(include_image_prompt=True)]},
    )
    validate_json_value(
        convert_node["outputs"],
        {
            "results": [
                {
                    "index": 1,
                    "paragraph_text": "鲁智深伏在林中。",
                    "panel_count": "1",
                    "present_characters": ["鲁智深"],
                    "location": "野猪林",
                    "key_props": [],
                    "segment_assignment": {},
                    "status": "failed",
                    "error": {"code": "structured_json_parse_failed", "message": "DeepSeek response is not valid JSON"},
                }
            ]
        },
    )

    assert prompt_review_node["ref"] == "ai.storyboard_review_refine.v1"
    assert prompt_review_node["inputs"]["items"] == {
        "from": "$nodes.convert_storyboard_plan_to_image_prompt.output.results",
    }
    assert prompt_review_node["inputs"]["max_revision_rounds"]["value"] == 1
    assert prompt_review_node["inputs"]["review_output_field"]["value"] == "prompt_review"
    assert prompt_review_node["inputs"]["review_history_output_field"]["value"] == "prompt_review_history"
    assert prompt_review_node["inputs"]["continue_on_item_error"]["value"] is True
    prompt_review_prompt = prompt_review_node["inputs"]["review_prompt_template"]["value"]
    prompt_revision_prompt = prompt_review_node["inputs"]["revision_prompt_template"]["value"]
    assert "画面提示词标准" in prompt_review_prompt
    assert "画面提示词标准" in prompt_revision_prompt
    assert "完整覆盖 panel_plan.panels 的每一格" in prompt_review_prompt
    assert "只检查 image_prompt 是否符合画面提示词标准" in prompt_review_prompt
    assert "不评价 panel_plan 本身是否最佳" in prompt_review_prompt
    assert "如果 panel_plan 本身不理想，也必须以它为既定事实" in prompt_review_prompt
    assert "整体情节方向" in prompt_review_prompt
    assert "声明的分格数量是否严格等于 panel_plan.panel_count" in prompt_review_prompt
    assert "每格出现的角色是否逐格对应 panel_plan" in prompt_review_prompt
    assert "前景、中景、背景各占画面大约多少" in prompt_review_prompt
    assert "每个镜头、空间和运动描述是否能看出画面目的" in prompt_review_prompt
    assert "不能压缩成短摘要" in prompt_revision_prompt
    assert "必须重新覆盖 panel_plan.panels 的全部分格" in prompt_revision_prompt
    assert "输出中的 think 写完整推理过程" in prompt_review_prompt
    assert "只返回 think 和 image_prompt" in prompt_revision_prompt
    assert "目标 JSON 示例" in prompt_review_prompt
    assert "目标 JSON 示例" in prompt_revision_prompt
    assert prompt_review_node["inputs"]["required_input_fields"]["value"] == ["scene_layout", "panel_plan", "image_prompt"]
    prompt_review_success_schema = _success_item_schema(prompt_review_node)
    assert {"think", "image_prompt", "prompt_review", "prompt_review_history"}.issubset(set(prompt_review_success_schema["required"]))
    assert "think" in prompt_review_success_schema["properties"]
    assert "完整覆盖所有分格" in prompt_review_prompt
    validate_json_value(
        prompt_review_node["outputs"],
        {"results": [_storyboard_segment_value(include_image_prompt=True)]},
    )
    validate_json_value(
        prompt_review_node["outputs"],
        {
            "results": [
                {
                    "index": 1,
                    "paragraph_text": "鲁智深伏在林中。",
                    "panel_count": "1",
                    "present_characters": ["鲁智深"],
                    "location": "野猪林",
                    "key_props": [],
                    "segment_assignment": {},
                    "status": "failed",
                    "error": {"code": "structured_json_parse_failed", "message": "DeepSeek response is not valid JSON"},
                }
            ]
        },
    )

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_prepare_storyboard_panel_cards_output_schema(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    node = _nodes_by_id(contract)["prepare_storyboard_panel_cards"]
    schema = node["outputs"]

    assert schema["type"] == "object"
    assert schema["required"] == ["panel_cards"]
    assert node["inputs"]["segment_descriptions"] == {
        "from": "$nodes.merge_segment_descriptions.output.segment_descriptions",
    }
    assert node["inputs"]["storyboard_items"] == {
        "from": "$nodes.prepare_segment_storyboard_inputs.output.items",
    }

    validate_json_value(
        schema,
        {
            "panel_cards": [
                {
                    "card_id": "segment-0",
                    "segment_index": 0,
                    "panel_index": 0,
                    "segment_title": "雪夜",
                    "description": "林冲披旧毡笠在风雪中前行。",
                    "image_prompt": "林冲披旧毡笠在风雪中前行。",
                    "prompt": "## 画面内容\n林冲披旧毡笠在风雪中前行。\n\n## 画面风格关键词\n风格指令：参考《罗小黑战记》。",
                    "reference_images": [
                        {
                            "label": "林冲",
                            "asset_type": "character",
                            "asset_name": "林冲",
                            "asset_tags": ["囚服雪地"],
                            "image_ref": {
                                "kind": "data_uri",
                                "data": "data:image/png;base64,bGluY2hvbmc=",
                                "role": "reference",
                            },
                            "source": "asset",
                        }
                    ],
                    "aspect_ratio": "16:9",
                    "resolution": "2K",
                }
            ],
        },
    )

    with pytest.raises(ValidationError):
        validate_json_value(schema, {})

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_review_storyboard_image_output_schema(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    schema = _nodes_by_id(contract)["review_storyboard_image"]["outputs"]
    node = _nodes_by_id(contract)["review_storyboard_image"]

    assert schema["type"] == "object"
    assert schema["required"] == ["decision", "panel_results"]
    assert node["name"] == "分镜汇总"
    assert node["ui"]["controls"]["interaction"]["control_id"] == "ui.interaction.storyboard_panel_cards.v1"
    validate_json_value(
        schema,
        {
            "decision": "finish",
            "panel_results": [
                {
                    "card_id": "segment-0",
                    "segment_index": 0,
                    "panel_index": 0,
                    "prompt": "分镜提示词",
                    "selected_image_url": "https://cdn.test/storyboard.png",
                }
            ],
        },
    )

    with pytest.raises(ValidationError):
        validate_json_value(
            schema,
            {"decision": "finish"},
        )

    validate_workflow_contract(contract, build_node_registry(test_settings))
