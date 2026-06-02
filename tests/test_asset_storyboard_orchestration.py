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

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_orchestration_workflow_node_list(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    nodes_by_id = _nodes_by_id(contract)
    assert list(nodes_by_id) == [
        "select_episode_metadata",
        "split_script",
        "assign_assets_to_segments",
        "resolve_segment_image_refs",
        "prepare_segment_storyboard_inputs",
        "describe_panels",
        "merge_segment_descriptions",
        "prepare_storyboard_panel_cards",
        "review_storyboard_image",
    ]
    assert {node_id: node["ref"] for node_id, node in nodes_by_id.items()} == {
        "select_episode_metadata": "tool.episode_metadata_from_asset.v1",
        "split_script": "tool.script_split.v1",
        "assign_assets_to_segments": "ai.deepseek_structured_json.v1",
        "resolve_segment_image_refs": "tool.resolve_segment_image_refs.v1",
        "prepare_segment_storyboard_inputs": "tool.prepare_segment_storyboard_inputs.v1",
        "describe_panels": "ai.parallel_deepseek_structured_json.v1",
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
        {"from": "split_script", "to": "assign_assets_to_segments"},
        {"from": "assign_assets_to_segments", "to": "resolve_segment_image_refs"},
        {"from": "resolve_segment_image_refs", "to": "prepare_segment_storyboard_inputs"},
        {"from": "prepare_segment_storyboard_inputs", "to": "describe_panels"},
        {"from": "describe_panels", "to": "merge_segment_descriptions"},
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

    assign_node = nodes_by_id["assign_assets_to_segments"]
    prompt_vars = assign_node["inputs"]["prompt"]["vars"]
    assert prompt_vars["segments"] == {"from": "$nodes.split_script.output.segments"}
    assert prompt_vars["asset_catalog"] == {
        "from": "$nodes.select_episode_metadata.output.asset_catalog",
    }
    assert prompt_vars["background"] == {
        "from": "$nodes.select_episode_metadata.output.background",
    }
    assert "不要拼接 image_ref" in assign_node["inputs"]["prompt"]["template"]
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
    assert prepare_node["inputs"]["segments"] == {
        "from": "$nodes.split_script.output.segments",
    }
    assert prepare_node["inputs"]["segment_assignments"] == {
        "from": "$nodes.resolve_segment_image_refs.output.segment_assignments",
    }

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_select_episode_metadata_schema_only_requires_episode_asset(
    test_settings,
) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    input_specs = _select_episode_inputs(contract)
    input_schema = input_specs["episode_asset_id"]["schema"]

    validate_json_value(input_schema, "asset_episode_001")
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
                            "asset_type": "character",
                            "asset_name": "林冲",
                            "asset_tags": ["囚服雪地"],
                            "asset_id": "asset-linchong",
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
                        }
                    ],
                    "key_props": ["花枪"],
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
                    "current_segment": {"index": 0, "text": "林冲踏雪而来。"},
                    "neighbor_segments": [],
                    "segment_assignment": {
                        "segment_index": 0,
                        "characters": [{"asset_type": "character", "asset_name": "林冲"}],
                        "key_props": [],
                    },
                }
            ],
            "shared_context": {
                "full_script": "完整剧本",
                "all_segments": [{"index": 0, "text": "林冲踏雪而来。"}],
            },
        },
    )

    with pytest.raises(ValidationError):
        validate_json_value(schema, {})

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_describe_panels_uses_parallel_segment_items(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    nodes_by_id = _nodes_by_id(contract)
    describe_node = nodes_by_id["describe_panels"]

    assert describe_node["ref"] == "ai.parallel_deepseek_structured_json.v1"
    assert describe_node["inputs"]["items"] == {
        "from": "$nodes.prepare_segment_storyboard_inputs.output.items",
    }
    assert describe_node["inputs"]["shared_context"] == {
        "from": "$nodes.prepare_segment_storyboard_inputs.output.shared_context",
    }
    assert "{item}" in describe_node["inputs"]["prompt_template"]["value"]
    assert "每次只为当前 item" in describe_node["inputs"]["system"]["value"]
    assert describe_node["inputs"]["prompt_fields"]["value"] == [
        "index",
        "current_segment",
        "neighbor_segments",
        "segment_assignment",
    ]
    assert describe_node["outputs"]["required"] == ["results"]

    validate_json_value(
        describe_node["outputs"],
        {
            "results": [
                {
                    "index": 0,
                    "segment_title": "雪夜",
                    "thinking": "承接风雪氛围。",
                    "panels": [
                        {
                            "description": "林冲在雪中行走。",
                            "style": "国风动画",
                            "constraints": "保持角色服饰一致。",
                        }
                    ],
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
        {
            "segment_descriptions": [
                {
                    "index": 0,
                    "segment_title": "雪夜",
                    "thinking": "承接风雪氛围。",
                    "panels": [
                        {
                            "description": "林冲在雪中行走。",
                            "style": "国风动画",
                            "constraints": "保持角色服饰一致。",
                        }
                    ],
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
                    "card_id": "segment-0-panel-0",
                    "segment_index": 0,
                    "panel_index": 0,
                    "segment_title": "雪夜",
                    "description": "林冲披旧毡笠在风雪中前行。",
                    "style": "电影感国风动画",
                    "constraints": "保持角色服装发型一致。",
                    "prompt": "分镜描述\n林冲披旧毡笠在风雪中前行。",
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
                    "card_id": "segment-0-panel-0",
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
