from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class MergeSegmentStoryboardDescriptionsNode(BaseNode):
    """合并并行生成的单段分镜描述。"""

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.merge_segment_storyboard_descriptions.v1",
            name="Merge Segment Storyboard Descriptions",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "required": ["results"],
                "properties": {
                    "results": {
                        "type": "array",
                        "items": _segment_description_schema(),
                    },
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["segment_descriptions"],
                "properties": {
                    "segment_descriptions": {
                        "type": "array",
                        "items": _segment_description_schema(),
                    }
                },
                "additionalProperties": False,
            },
            description="按 index 排序并合并 ai.parallel_deepseek_structured_json.v1 的单段分镜结果。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        _ = ctx
        results = inputs.get("results")
        if not isinstance(results, list):
            raise ValidationError(
                code="segment_storyboard_results_required",
                message="results must be an array",
            )

        descriptions = [dict(item) for item in results if isinstance(item, Mapping)]
        descriptions.sort(key=lambda item: _sort_index(item.get("index")))
        return NodeResult(status="succeeded", output={"segment_descriptions": descriptions})


def _segment_description_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["index", "segment_title", "thinking", "panels"],
        "properties": {
            "index": {"type": "integer", "minimum": 0},
            "segment_title": {"type": "string", "minLength": 1},
            "thinking": {"type": "string", "minLength": 1},
            "panels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["description", "style", "constraints"],
                    "properties": {
                        "description": {"type": "string", "minLength": 1},
                        "style": {"type": "string", "minLength": 1},
                        "constraints": {"type": "string", "minLength": 1},
                        "character_focus": {"type": "string"},
                        "environment_details": {"type": "string"},
                        "shot_type": {"type": "string"},
                        "camera_angle": {"type": "string"},
                        "composition": {"type": "string"},
                        "lighting": {"type": "string"},
                        "mood": {"type": "string"},
                        "action": {"type": "string"},
                        "key_props": {"type": "string"},
                        "continuity_notes": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
        },
        "additionalProperties": False,
    }


def _sort_index(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
