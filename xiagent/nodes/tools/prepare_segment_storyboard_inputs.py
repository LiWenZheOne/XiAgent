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
                                "neighbor_segments",
                                "segment_assignment",
                            ],
                            "properties": {
                                "index": {"type": "integer", "minimum": 0},
                                "current_segment": {"type": "object"},
                                "neighbor_segments": {"type": "array", "items": {"type": "object"}},
                                "segment_assignment": {"type": "object"},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "shared_context": {
                        "type": "object",
                        "required": ["full_script", "all_segments"],
                        "properties": {
                            "full_script": {"type": "string", "minLength": 1},
                            "all_segments": {"type": "array", "items": {"type": "object"}},
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

        assignment_by_index = {
            int(assignment["segment_index"]): dict(assignment)
            for assignment in segment_assignments
            if "segment_index" in assignment and _is_int_like(assignment["segment_index"])
        }

        items: list[dict[str, Any]] = []
        for position, segment in enumerate(segments):
            if "index" not in segment or not _is_int_like(segment["index"]):
                continue
            index = int(segment["index"])
            items.append(
                {
                    "index": index,
                    "current_segment": dict(segment),
                    "neighbor_segments": _neighbor_segments(segments, position),
                    "segment_assignment": assignment_by_index.get(
                        index,
                        {"segment_index": index, "characters": [], "key_props": []},
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
                    "all_segments": [dict(item) for item in segments],
                },
            },
        )


def _neighbor_segments(segments: list[dict[str, Any]], position: int) -> list[dict[str, Any]]:
    neighbors: list[dict[str, Any]] = []
    for index in (position - 1, position + 1):
        if 0 <= index < len(segments):
            neighbors.append(dict(segments[index]))
    return neighbors


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
