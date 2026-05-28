from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class SystemUserInputNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="system.user_input.v1",
            name="User Input",
            version="1.0.0",
            kind="system",
            input_schema={
                "type": "object",
                "additionalProperties": True,
            },
            output_schema={
                "type": "object",
                "additionalProperties": True,
            },
            description="等待用户填写结构化输入，并把输入作为节点输出传递给下游。",
            ui_defaults={
                "controls": {
                    "input": {
                        "control_id": "ui.input.schema_form.v1",
                        "variant": "default",
                        "mode": "input",
                    },
                    "output": {
                        "control_id": "ui.input.schema_form.v1",
                        "variant": "default",
                        "mode": "readonly",
                    },
                }
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        return NodeResult(status="succeeded", output=dict(inputs))
