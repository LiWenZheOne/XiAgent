from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class SystemUserChoiceNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="system.user_choice.v1",
            name="User Choice",
            version="1.0.0",
            kind="system",
            input_schema={
                "type": "object",
                "required": ["candidates"],
                "properties": {
                    "question": {"type": "string"},
                    "candidates": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["id"],
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                                "image_url": {"type": "string"},
                                "asset_id": {"type": "string"},
                                "value": {},
                            },
                            "additionalProperties": True,
                        },
                    },
                },
                "additionalProperties": True,
            },
            output_schema={
                "type": "object",
                "required": ["selected_id", "selected_item"],
                "properties": {
                    "selected_id": {"type": "string"},
                    "selected_index": {"type": "integer", "minimum": 0},
                    "selected_item": {"type": "object", "additionalProperties": True},
                    "selected_image_url": {"type": "string"},
                },
                "additionalProperties": True,
            },
            description="暂停工作流并等待用户从候选项中选择一个结果。",
            ui_defaults={
                "controls": {
                    "interaction": {
                        "control_id": "ui.choice.image_three.v1",
                        "variant": "equal_grid",
                        "mode": "interactive",
                        "bindings": {
                            "items_path": "$node.input.candidates",
                            "image_url_path": "image_url",
                            "value_path": "id",
                        },
                    }
                }
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        candidates = list(inputs.get("candidates", []))
        question = inputs.get("question")
        return NodeResult(
            status="waiting",
            output={},
            metadata={
                "question": question if isinstance(question, str) else "请选择一个结果",
                "candidates": candidates,
                "selection_mode": "single",
            },
        )
