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


def test_orchestration_workflow_contract_structure(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    assert contract["workflow"]["id"] == "asset_storyboard_generation"
    assert contract["workflow"]["version"] == "1.1.0"
    assert contract["workflow"]["scope"] == "global"
    assert contract["workflow"]["name"] == "分镜生成"

    select_outputs = _select_episode_outputs(contract)
    assert select_outputs["required"] == ["episode_asset_id"]
    assert "storyboard_target" not in select_outputs["required"]

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_orchestration_workflow_node_list(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    nodes_by_id = _nodes_by_id(contract)
    assert list(nodes_by_id) == [
        "select_episode_metadata",
        "load_episode_metadata",
        "confirm_episode_context",
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
        "select_episode_metadata": "system.user_input.v1",
        "load_episode_metadata": "tool.episode_metadata_from_asset.v1",
        "confirm_episode_context": "system.human_approval.v1",
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


def test_orchestration_workflow_edges_are_linear_dag(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)

    assert [edge for edge in contract["edges"] if "when" in edge] == []
    assert contract["edges"] == [
        {"from": "START", "to": "select_episode_metadata"},
        {"from": "select_episode_metadata", "to": "load_episode_metadata"},
        {"from": "load_episode_metadata", "to": "confirm_episode_context"},
        {"from": "confirm_episode_context", "to": "split_script"},
        {"from": "split_script", "to": "assign_assets_to_segments"},
        {"from": "assign_assets_to_segments", "to": "assemble_storyboard_context"},
        {"from": "assemble_storyboard_context", "to": "describe_panels"},
        {"from": "describe_panels", "to": "review_storyboard_prompt"},
        {"from": "review_storyboard_prompt", "to": "extract_panel_image_urls"},
        {"from": "extract_panel_image_urls", "to": "assemble_prompt_v2"},
        {"from": "assemble_prompt_v2", "to": "generate_image_v2"},
        {"from": "generate_image_v2", "to": "review_storyboard_image"},
        {"from": "review_storyboard_image", "to": "END"},
    ]

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_episode_confirmation_collects_editable_episode_context(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    nodes_by_id = _nodes_by_id(contract)

    load_node = nodes_by_id["load_episode_metadata"]
    assert load_node["inputs"]["episode_asset_id"] == {
        "from": "$nodes.select_episode_metadata.output.episode_asset_id",
    }
    select_ui = nodes_by_id["select_episode_metadata"]["ui"]["controls"]["input"]
    assert select_ui["options"]["fields"]["episode_asset_id"] == {
        "control_id": "ui.input.asset_picker.v1",
        "variant": "list",
        "mode": "input",
        "asset_type": "text",
        "filter_tag_names": ["集元数据"],
        "button_label": "选择集",
        "dialog_title": "选择集信息资产",
    }
    assert "source_script" in load_node["outputs"]["required"]
    assert "asset_catalog" in load_node["outputs"]["required"]

    confirm_node = nodes_by_id["confirm_episode_context"]
    assert set(confirm_node["inputs"]) >= {
        "question",
        "episode_name",
        "episode_summary",
        "source_script",
        "background",
        "asset_catalog",
        "storyboard_target",
    }
    for input_name in [
        "episode_name",
        "episode_summary",
        "source_script",
        "background",
        "asset_catalog",
        "storyboard_target",
    ]:
        assert confirm_node["inputs"][input_name]["from_user"] is True

    assert confirm_node["outputs"]["required"] == [
        "episode_name",
        "source_script",
        "background",
        "asset_catalog",
        "storyboard_target",
    ]

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_episode_context_drives_segment_asset_assignment(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    nodes_by_id = _nodes_by_id(contract)

    split_node = nodes_by_id["split_script"]
    assert split_node["inputs"]["script"] == {
        "from": "$nodes.confirm_episode_context.output.source_script",
    }
    assert "background" not in split_node["inputs"]

    assign_node = nodes_by_id["assign_assets_to_segments"]
    prompt_vars = assign_node["inputs"]["prompt"]["vars"]
    assert prompt_vars["segments"] == {"from": "$nodes.split_script.output.segments"}
    assert prompt_vars["asset_catalog"] == {
        "from": "$nodes.confirm_episode_context.output.asset_catalog",
    }
    assert prompt_vars["background"] == {
        "from": "$nodes.confirm_episode_context.output.background",
    }

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_select_episode_metadata_schema_storyboard_target_default(
    test_settings,
) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    input_schema = _select_episode_outputs(contract)

    validate_json_value(input_schema, {"episode_asset_id": "asset_episode_001"})
    validate_json_value(
        input_schema,
        {
            "episode_asset_id": "asset_episode_001",
            "storyboard_target": {"segment_index": 2, "panel_index": 1},
        },
    )

    storyboard_target = input_schema["properties"]["storyboard_target"]
    assert storyboard_target["properties"]["segment_index"]["default"] == 0
    assert storyboard_target["properties"]["panel_index"]["default"] == 0

    with pytest.raises(ValidationError):
        validate_json_value(input_schema, {"storyboard_target": {}})

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
                            "full_name": "林冲",
                            "image_ref": {
                                "kind": "data_uri",
                                "data": "data:image/png;base64,bGluY2hvbmc=",
                                "role": "reference",
                            },
                            "variant": "囚服雪地",
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


def test_assemble_storyboard_context_output_schema(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    schema = _nodes_by_id(contract)["assemble_storyboard_context"]["outputs"]

    assert schema["type"] == "object"
    assert "context_string" in schema["required"]
    validate_json_value(schema, {"context_string": "段落0：林冲踏雪而来..."})

    with pytest.raises(ValidationError):
        validate_json_value(schema, {})

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_extract_panel_image_urls_output_schema(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    schema = _nodes_by_id(contract)["extract_panel_image_urls"]["outputs"]

    assert schema["type"] == "object"
    for key in ["panel_image_refs", "image_refs", "description", "style", "constraints"]:
        assert key in schema["required"]

    validate_json_value(
        schema,
        {
            "panel_image_refs": [
                {
                    "full_name": "林冲",
                    "image_ref": {
                        "kind": "data_uri",
                        "data": "data:image/png;base64,bGluY2hvbmc=",
                        "role": "reference",
                    },
                    "variant": "囚服雪地",
                }
            ],
            "image_refs": [
                {
                    "kind": "data_uri",
                    "data": "data:image/png;base64,bGluY2hvbmc=",
                    "role": "reference",
                }
            ],
            "description": "林冲披旧毡笠在风雪中前行。",
            "style": "电影感国风动画",
            "constraints": "保持角色服装发型一致。",
        },
    )
    validate_json_value(
        schema,
        {
            "panel_image_refs": [],
            "image_refs": [],
            "description": "空场景无角色。",
            "style": "默认风格",
            "constraints": "无约束。",
        },
    )

    with pytest.raises(ValidationError):
        validate_json_value(
            schema,
            {
                "panel_image_refs": [],
                "image_refs": [],
                "style": "默认风格",
                "constraints": "无约束。",
            },
        )

    validate_workflow_contract(contract, build_node_registry(test_settings))


def test_review_storyboard_image_output_schema(test_settings) -> None:
    contract = load_workflow_file(ORCHESTRATION_WORKFLOW_PATH)
    schema = _nodes_by_id(contract)["review_storyboard_image"]["outputs"]

    assert schema["type"] == "object"
    assert "decision" in schema["required"]
    validate_json_value(schema, {"decision": "approve"})
    validate_json_value(schema, {"decision": "reject"})

    with pytest.raises(ValidationError):
        validate_json_value(
            schema,
            {"selected_image_url": "https://cdn.test/storyboard.png"},
        )

    validate_workflow_contract(contract, build_node_registry(test_settings))
