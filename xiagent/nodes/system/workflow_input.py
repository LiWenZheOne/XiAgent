from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class WorkflowInputNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="system.workflow_input.v1",
            name="Workflow Input",
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
            description="暂停工作流并等待用户填写本次运行输入。",
            ui_defaults={
                "controls": {
                    "interaction": {
                        "control_id": "ui.input.schema_form.v1",
                        "variant": "default",
                        "mode": "input",
                    }
                }
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        output_schema = dict(ctx.output_schema) if ctx is not None else {}
        config = dict(ctx.config) if ctx is not None else {}
        return NodeResult(
            status="waiting",
            output={},
            metadata={
                "input_schema": output_schema,
                "title": str(config.get("title") or "填写运行输入"),
                "description": str(config.get("description") or ""),
                "requested_inputs": dict(inputs),
            },
        )
