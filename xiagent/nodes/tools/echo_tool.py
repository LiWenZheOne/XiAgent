from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class EchoToolNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.echo.v1",
            name="Echo Tool",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "additionalProperties": True,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "echo": {"type": "object"},
                },
                "required": ["echo"],
                "additionalProperties": False,
            },
            description="返回输入数据，用于节点执行链路测试。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        return NodeResult(status="succeeded", output={"echo": dict(inputs)})
