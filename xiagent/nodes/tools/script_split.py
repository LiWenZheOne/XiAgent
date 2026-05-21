from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult

_PANEL_HINT_PATTERN = re.compile(r"^\s*[\(（](\d+)(?:\s*-\s*(\d+))?[\)）]\s*")


class ScriptSplitNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.script_split.v1",
            name="Script Split",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "script": {"type": "string", "minLength": 1},
                },
                "required": ["script"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "minimum": 0},
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
                            "required": [
                                "index",
                                "text",
                                "panel_hint",
                                "panel_count_min",
                                "panel_count_max",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["count", "segments"],
                "additionalProperties": False,
            },
            description="Split a script into storyboard segments and extract panel count hints.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        script = inputs.get("script")
        if not isinstance(script, str) or not script.strip():
            raise ValidationError(
                code="script_required",
                message="Script cannot be empty",
            )

        segments: list[dict[str, Any]] = []
        for raw_part in re.split(r"(?:\r?\n){2,}", script):
            text = raw_part.strip()
            if not text:
                continue

            hint_match = _PANEL_HINT_PATTERN.match(text)
            if hint_match is None:
                panel_hint = "1"
                panel_min = 1
                panel_max = 1
            else:
                first = int(hint_match.group(1))
                second_text = hint_match.group(2)
                second = int(second_text) if second_text is not None else first
                panel_min = min(first, second)
                panel_max = max(first, second)
                panel_hint = str(first) if second_text is None else f"{first}-{second}"
                text = text[hint_match.end() :].strip()
                if not text:
                    continue

            segments.append(
                {
                    "index": len(segments),
                    "text": text,
                    "panel_hint": panel_hint,
                    "panel_count_min": panel_min,
                    "panel_count_max": panel_max,
                }
            )

        return NodeResult(
            status="succeeded",
            output={"count": len(segments), "segments": segments},
        )
