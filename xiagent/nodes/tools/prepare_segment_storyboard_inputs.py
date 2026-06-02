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
                                "current_segment",
                                "segment_assignment",
                            ],
                            "properties": {
                                "index": {"type": "integer", "minimum": 0},
                                "current_segment": {"type": "object"},
                                "segment_assignment": {"type": "object"},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "shared_context": {
                        "type": "object",
                        "required": ["full_script"],
                        "properties": {
                            "full_script": {"type": "string", "minLength": 1},
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
                },
                "additionalProperties": False,
            },
            description="为每个剧本段落构造独立分镜生成 item，供并行结构化 LLM 节点逐段处理。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        _ = ctx
        source_script = _required_text(inputs.get("source_script"), "source_script_required")
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
            items.append(
                {
                    "index": index,
                    "current_segment": dict(segment),
                    "segment_assignment": _compact_assignment(
                        assignment_by_index.get(
                            index,
                            {"segment_index": index, "characters": [], "key_props": []},
                        )
                    ),
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
                    "storyboard_options": storyboard_options,
                },
            },
        )


def _required_text(value: Any, code: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValidationError(code=code, message=f"{code} must be a non-empty string")


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
