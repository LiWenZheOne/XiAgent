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
        descriptions.sort(
            key=lambda item: (
                _sort_index(item.get("index")),
                _sort_index(item.get("prompt_variant_index")),
            )
        )
        return NodeResult(status="succeeded", output={"segment_descriptions": descriptions})


def _segment_description_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["index"],
        "properties": {
            "index": {"type": "integer", "minimum": 0},
            "segment_title": {"type": "string", "minLength": 1},
            "thinking": {"type": "string", "minLength": 1},
            "description": {"type": "string", "minLength": 1},
            "scene_layout": {"type": "object", "additionalProperties": True},
            "panel_plan": {"type": "object", "additionalProperties": True},
            "prompt_variant_index": {"type": "integer", "minimum": 0},
            "prompt_variant_count": {"type": "integer", "minimum": 1},
            "prompt_variant_instruction": {"type": "string"},
            "image_prompt": {"type": "string", "minLength": 1},
            "review": {"type": "object", "additionalProperties": True},
            "review_history": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "prompt_review": {"type": "object", "additionalProperties": True},
            "prompt_review_history": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "status": {"type": "string"},
            "error": {"type": "object", "additionalProperties": True},
        },
        "additionalProperties": True,
    }


def _sort_index(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
