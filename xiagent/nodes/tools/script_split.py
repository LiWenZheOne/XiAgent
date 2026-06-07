from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult

_PANEL_HINT_PATTERN = re.compile(r"^\s*[\(（]\s*([0-9０-９]*)(?:\s*[-－—–~～]\s*([0-9０-９]+))?\s*[\)）]\s*")
_PANEL_MARKER_PATTERN = re.compile(r"[\(（]\s*([0-9０-９]*)(?:\s*[-－—–~～]\s*([0-9０-９]+))?\s*[\)）]")
_AUTO_PANEL_HINT = "auto"


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
                    "max_segments": {"type": "integer", "minimum": 1},
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
            description="Split a script into storyboard segments without treating marker numbers as panel count hints.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        script = inputs.get("script")
        if not isinstance(script, str) or not script.strip():
            raise ValidationError(
                code="script_required",
                message="Script cannot be empty",
            )

        max_segments = inputs.get("max_segments")
        if (
            max_segments is not None
            and (
                not isinstance(max_segments, int)
                or isinstance(max_segments, bool)
                or max_segments < 1
            )
        ):
            raise ValidationError(
                code="max_segments_invalid",
                message="max_segments must be an integer greater than or equal to 1",
            )

        segments: list[dict[str, Any]] = []
        raw_segments = _split_marked_segments(script)
        if not raw_segments:
            raw_segments = [(None, None, raw_part) for raw_part in re.split(r"(?:\r?\n){2,}", script)]

        for marker_min, marker_max, raw_part in raw_segments:
            text = raw_part.strip()
            if not text:
                continue

            if marker_min is None:
                hint_match = _PANEL_HINT_PATTERN.match(text)
            else:
                hint_match = None

            if marker_min is not None:
                panel_min, panel_max, panel_hint = _auto_panel_counts()
            elif hint_match is None:
                panel_min, panel_max, panel_hint = _auto_panel_counts()
            else:
                panel_min, panel_max, panel_hint = _auto_panel_counts()
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
            if max_segments is not None and len(segments) >= max_segments:
                break

        return NodeResult(
            status="succeeded",
            output={"count": len(segments), "segments": segments},
        )


def _split_marked_segments(script: str) -> list[tuple[str | None, str | None, str]]:
    matches = list(_PANEL_MARKER_PATTERN.finditer(script))
    if not matches:
        return []

    segments: list[tuple[str | None, str | None, str]] = []
    prefix = script[: matches[0].start()].strip()
    if prefix:
        segments.append((None, None, prefix))

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(script)
        segments.append((match.group(1), match.group(2), script[start:end]))
    return segments


def _auto_panel_counts() -> tuple[int, int, str]:
    return 1, 1, _AUTO_PANEL_HINT
