from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class AssembleSegmentContextNode(BaseNode):
    """将多段剧本分析与分格提示格式化为可注入 LLM prompt 的上下文文本。"""

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.assemble_segment_context.v1",
            name="Assemble Segment Context",
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
                    "segment_analyses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "index": {"type": "integer", "minimum": 0},
                                "thinking": {"type": "string"},
                                "location": {"type": "string"},
                                "time": {"type": "string"},
                                "characters": {"type": "object", "additionalProperties": True},
                            },
                            "required": ["index", "characters"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["segments", "segment_analyses"],
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
            description="Format segments and character analyses into a human-readable context string for LLM prompts.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        segments = _required_list(inputs, "segments")
        segment_analyses = _required_list(inputs, "segment_analyses")

        analysis_by_index: dict[int, dict[str, Any]] = {}
        for analysis in segment_analyses:
            if isinstance(analysis, dict) and "index" in analysis:
                analysis_by_index[int(analysis["index"])] = analysis

        parts: list[str] = []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            index = int(segment.get("index", 0))
            text = str(segment.get("text", "")).strip()
            parts.append(f"--- 段落 {index} ---")
            parts.append(f"原文：{text}")
            parts.append("分格数策略：由 AI 根据本段情节、动作密度和情绪节奏自行设计。")

            analysis = analysis_by_index.get(index)
            if analysis is not None:
                location = str(analysis.get("location", "")).strip()
                time = str(analysis.get("time", "")).strip()
                if location:
                    parts.append(f"地点：{location}")
                if time:
                    parts.append(f"时间：{time}")

                characters = analysis.get("characters")
                if isinstance(characters, dict) and characters:
                    parts.append("在场角色：")
                    for char_name, char_info in characters.items():
                        if isinstance(char_info, dict):
                            clothing = str(char_info.get("clothing", "未指定")).strip()
                            event = str(char_info.get("event", "")).strip()
                            aliases = char_info.get("aliases", [])
                            aliases_str = ", ".join(str(a) for a in aliases if isinstance(a, str)) if isinstance(aliases, list) else ""
                            line = f"  - {char_name}"
                            if clothing and clothing != "未指定":
                                line += f"（服装：{clothing}）"
                            if event:
                                line += f"（状态：{event}）"
                            if aliases_str:
                                line += f"（别名：{aliases_str}）"
                            parts.append(line)
                        else:
                            parts.append(f"  - {char_name}")
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


def _required_list(inputs: Mapping[str, Any], key: str) -> list[Any]:
    value = inputs.get(key)
    if not isinstance(value, list):
        raise ValidationError(
            code=f"{key}_required",
            message=f"{key} must be an array",
        )
    return value
