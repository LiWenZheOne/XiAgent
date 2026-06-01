from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class AssembleStoryboardContextNode(BaseNode):
    """将段落在场资产分配格式化为可注入 LLM prompt 的上下文字符串。"""

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.assemble_storyboard_context.v1",
            name="Assemble Storyboard Context",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "segments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "index": {"type": "integer", "minimum": 0},
                                "text": {"type": "string", "minLength": 1},
                                "panel_hint": {"type": "string", "minLength": 1},
                                "panel_count_min": {"type": "integer", "minimum": 1},
                                "panel_count_max": {"type": "integer", "minimum": 1},
                            },
                            "required": ["index", "text", "panel_hint", "panel_count_min", "panel_count_max"],
                            "additionalProperties": False,
                        },
                    },
                    "segment_assignments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "segment_index": {"type": "integer", "minimum": 0},
                                "location": {"type": "string"},
                                "time": {"type": "string"},
                                "characters": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "full_name": {"type": "string", "minLength": 1},
                                            "variant": {"type": "string"},
                                            "image_ref": {
                                                "type": "object",
                                                "properties": {
                                                    "kind": {"type": "string"},
                                                    "asset_id": {"type": "string"},
                                                    "data": {"type": "string"},
                                                    "role": {"type": "string"},
                                                },
                                                "additionalProperties": False,
                                            },
                                            "image_url": {"type": "string"},
                                            "accessories": {"type": ["string", "array"]},
                                        },
                                        "required": ["full_name"],
                                        "additionalProperties": False,
                                    },
                                },
                                "key_props": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["segment_index"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["segments", "segment_assignments"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "context_string": {"type": "string", "minLength": 1},
                },
                "required": ["context_string"],
                "additionalProperties": False,
            },
            description="Format segments and segment asset assignments into a human-readable context string for LLM prompts.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        segments = _required_list(inputs, "segments")
        segment_assignments = _required_list(inputs, "segment_assignments")

        assignment_by_index: dict[int, dict[str, Any]] = {}
        for assignment in segment_assignments:
            if isinstance(assignment, dict) and "segment_index" in assignment:
                assignment_by_index[int(assignment["segment_index"])] = assignment

        parts: list[str] = []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            index = int(segment.get("index", 0))
            text = str(segment.get("text", "")).strip()
            panel_hint = str(segment.get("panel_hint", "1"))
            panel_min = int(segment.get("panel_count_min", 1))
            panel_max = int(segment.get("panel_count_max", 1))

            parts.append(f"--- 段落 {index} ---")
            parts.append(f"原文：{text}")
            parts.append(f"建议分格数：{panel_hint}（最少 {panel_min} 格，最多 {panel_max} 格）")

            assignment = assignment_by_index.get(index)
            if assignment is not None:
                location = str(assignment.get("location", "")).strip()
                time = str(assignment.get("time", "")).strip()
                if location:
                    parts.append(f"地点：{location}")
                if time:
                    parts.append(f"时间：{time}")

                # present assets: try "characters" first (YAML convention), fallback
                present_assets = assignment.get("characters") or assignment.get("present_assets")
                if isinstance(present_assets, list) and present_assets:
                    parts.append("在场资产：")
                    for asset_item in present_assets:
                        if not isinstance(asset_item, dict):
                            continue
                        full_name = str(asset_item.get("full_name", "")).strip()
                        if not full_name:
                            continue
                        variant = str(asset_item.get("variant", "")).strip()
                        image_url = str(asset_item.get("image_url", "")).strip()
                        image_ref = _format_image_ref(asset_item.get("image_ref"))
                        accessories = asset_item.get("accessories", "")
                        accessories_str = _format_accessories(accessories)
                        parts.append(
                            f"  - {full_name}（变体：{variant}）（参考图：{image_ref or image_url}）（配件：{accessories_str}）"
                        )
            parts.append("")

        context_string = "\n".join(parts)
        if not context_string.strip():
            raise ValidationError(
                code="empty_context",
                message="Assembled context string is empty",
            )

        return NodeResult(
            status="succeeded",
            output={"context_string": context_string},
        )


def _format_accessories(accessories: Any) -> str:
    """Convert accessories to a string representation."""
    if isinstance(accessories, list):
        return "、".join(str(a) for a in accessories if a)
    return str(accessories).strip() if accessories else ""


def _format_image_ref(image_ref: Any) -> str:
    if not isinstance(image_ref, Mapping):
        return ""
    kind = str(image_ref.get("kind", "")).strip()
    if kind == "asset":
        asset_id = str(image_ref.get("asset_id", "")).strip()
        return f"asset:{asset_id}" if asset_id else ""
    if kind == "data_uri":
        return "data_uri:image"
    return ""


def _required_list(inputs: Mapping[str, Any], key: str) -> list[Any]:
    value = inputs.get(key)
    if not isinstance(value, list):
        raise ValidationError(
            code=f"{key}_required",
            message=f"{key} must be an array",
        )
    return value
