from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class PrepareSegmentStoryboardInputsNode(BaseNode):
    """把完整剧本、拆分段落和段落资产分配整理成逐段分镜生成输入。"""

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.prepare_segment_storyboard_inputs.v1",
            name="Prepare Segment Storyboard Inputs",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "required": ["source_script", "segments", "segment_assignments"],
                "properties": {
                    "source_script": {"type": "string", "minLength": 1},
                    "world_background": {"type": "string"},
                    "segments": {"type": "array", "items": {"type": "object"}},
                    "segment_assignments": {"type": "array", "items": {"type": "object"}},
                    "storyboard_options": {
                        "type": "object",
                        "properties": {
                            "no_material": {"type": "boolean"},
                            "enrich_description": {"type": "boolean"},
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["items", "shared_context"],
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": [
                                "index",
                                "paragraph_text",
                                "panel_count",
                                "present_characters",
                                "location",
                                "scene_description",
                                "key_props",
                                "segment_assignment",
                            ],
                            "properties": {
                                "index": {"type": "integer", "minimum": 0},
                                "paragraph_text": {"type": "string", "minLength": 1},
                                "panel_count": {"type": "string", "minLength": 1},
                                "present_characters": {
                                    "type": "array",
                                    "items": {"type": "string", "minLength": 1},
                                },
                                "location": {"type": "string"},
                                "scene_description": {"type": "string"},
                                "key_props": {
                                    "type": "array",
                                    "items": {"type": "string", "minLength": 1},
                                },
                                "segment_assignment": {"type": "object"},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "shared_context": {
                        "type": "object",
                        "required": ["full_script", "world_background", "prompt_rules"],
                        "properties": {
                            "full_script": {"type": "string", "minLength": 1},
                            "world_background": {"type": "string"},
                            "storyboard_options": {
                                "type": "object",
                                "properties": {
                                    "no_material": {"type": "boolean"},
                                    "enrich_description": {"type": "boolean"},
                                },
                                "additionalProperties": False,
                            },
                            "prompt_rules": {
                                "type": "object",
                                "required": [
                                    "material_rule",
                                    "enrich_rule",
                                    "material_thinking",
                                    "enrich_thinking",
                                ],
                                "properties": {
                                    "material_rule": {"type": "string"},
                                    "enrich_rule": {"type": "string"},
                                    "material_thinking": {"type": "string"},
                                    "enrich_thinking": {"type": "string"},
                                },
                                "additionalProperties": False,
                            },
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
            description="为每个剧本段落构造独立分镜生成 item，供并行结构化 LLM 节点逐段处理。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        _ = ctx
        source_script = _required_text(inputs.get("source_script"), "source_script_required")
        world_background = _text(inputs.get("world_background"))
        segments = _required_object_list(inputs.get("segments"), "segments_required")
        segment_assignments = _required_object_list(
            inputs.get("segment_assignments"),
            "segment_assignments_required",
        )
        storyboard_options = _storyboard_options(inputs.get("storyboard_options"))

        assignment_by_index = {
            int(assignment["segment_index"]): dict(assignment)
            for assignment in segment_assignments
            if "segment_index" in assignment and _is_int_like(assignment["segment_index"])
        }

        items: list[dict[str, Any]] = []
        for segment in segments:
            if "index" not in segment or not _is_int_like(segment["index"]):
                continue
            index = int(segment["index"])
            raw_assignment = assignment_by_index.get(
                index,
                {"segment_index": index, "characters": [], "key_props": []},
            )
            assignment = _compact_assignment(raw_assignment)
            items.append(
                {
                    "index": index,
                    "paragraph_text": _text(segment.get("text")),
                    "panel_count": _panel_count(segment),
                    "present_characters": _present_character_names(assignment),
                    "location": _text(assignment.get("location")),
                    "scene_description": _scene_description(raw_assignment),
                    "key_props": _string_list(assignment.get("key_props")),
                    "segment_assignment": assignment,
                }
            )

        if not items:
            raise ValidationError(
                code="segment_storyboard_items_empty",
                message="No valid segment storyboard items can be prepared",
            )

        return NodeResult(
            status="succeeded",
            output={
                "items": items,
                "shared_context": {
                    "full_script": source_script,
                    "world_background": world_background,
                    "storyboard_options": storyboard_options,
                    "prompt_rules": _prompt_rules(storyboard_options),
                },
            },
        )


def _required_text(value: Any, code: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValidationError(code=code, message=f"{code} must be a non-empty string")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _required_object_list(value: Any, code: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValidationError(code=code, message=f"{code} must be an array")
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _is_int_like(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _storyboard_options(value: Any) -> dict[str, bool]:
    options = dict(value) if isinstance(value, Mapping) else {}
    return {
        "no_material": options.get("no_material") is True,
        "enrich_description": options.get("enrich_description") is True,
    }


def _prompt_rules(options: Mapping[str, bool]) -> dict[str, str]:
    if options.get("no_material") is True:
        material_rule = (
            "- 删除所有材质和质感审查，只保留空间、结构、色彩、光影、功能和动作信息。"
        )
        material_thinking = "不讨论材质、质地、面料、纹理、锈蚀、丝滑、粗糙等质感信息。"
    else:
        material_rule = "- 可以描述对画面叙事必要的材质和表面质感，但不要堆砌材质词。"
        material_thinking = "如材质或表面状态能服务身份、年代、动作或情绪，可以简洁说明。"

    if options.get("enrich_description") is True:
        enrich_rule = (
            "- 额外落实：能否增加遮挡物强化窥视感和空间深度；动作是否造成飘动、飞溅、"
            "散落、震动等物理反馈；建筑结构和陈设是否足够具体；空气中是否有尘、雪、烟、"
            "雾、火星等颗粒介质；是否有能暗示身份、地位或心境的细小物件。"
        )
        enrich_thinking = (
            "逐项补充遮挡物、空间深度、物理反馈、建筑陈设、颗粒介质和细小叙事物件，"
            "并把有效结果写入 image_prompt。"
        )
    else:
        enrich_rule = "- 保持描述清晰克制，不追加额外密度审查。"
        enrich_thinking = "不额外扩写空间深度、物理反馈、复杂陈设、颗粒介质或细小叙事物件。"

    return {
        "material_rule": material_rule,
        "enrich_rule": enrich_rule,
        "material_thinking": material_thinking,
        "enrich_thinking": enrich_thinking,
    }


def _panel_count(segment: Mapping[str, Any]) -> str:
    hint = _text(segment.get("panel_hint"))
    if hint:
        return hint
    minimum = segment.get("panel_count_min")
    maximum = segment.get("panel_count_max")
    if _is_int_like(minimum) and _is_int_like(maximum):
        if minimum == maximum:
            return str(minimum)
        return f"{minimum}-{maximum}"
    return "1"


def _compact_assignment(assignment: Mapping[str, Any]) -> dict[str, Any]:
    characters = [
        character
        for character in (_compact_character(item) for item in _object_list(assignment.get("characters")))
        if character
    ]
    result: dict[str, Any] = {
        "segment_index": assignment.get("segment_index"),
        "characters": characters,
        "key_props": _string_list(assignment.get("key_props")),
    }
    for key in ("location", "time"):
        value = assignment.get(key)
        if isinstance(value, str):
            result[key] = value.strip()
    return result


def _scene_description(assignment: Mapping[str, Any]) -> str:
    location_asset = assignment.get("location_asset")
    if isinstance(location_asset, Mapping):
        description = _text(location_asset.get("description"))
        if description:
            return description
    return _text(assignment.get("scene_description"))


def _present_character_names(assignment: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for character in _object_list(assignment.get("characters")):
        presence = _text(character.get("presence"))
        if presence and presence != "present":
            continue
        name = _text(character.get("asset_name"))
        if name:
            names.append(name)
    return names


def _compact_character(character: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in (
        "asset_name",
        "asset_tags",
        "appearance_description",
        "presence",
    ):
        value = character.get(key)
        if key == "asset_tags":
            tags = _string_list(value)
            if tags:
                result[key] = tags
        elif isinstance(value, str) and value.strip():
            result[key] = value.strip()
    return result


def _object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
