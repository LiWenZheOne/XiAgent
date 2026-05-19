from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class HumanApprovalNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="system.human_approval.v1",
            name="Human Approval",
            version="1.0.0",
            kind="system",
            input_schema={
                "type": "object",
                "additionalProperties": True,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "decision": {"type": "string"},
                },
                "required": ["decision"],
                "additionalProperties": True,
            },
            description="暂停工作流并等待人工审批输入。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        return NodeResult(
            status="waiting",
            output={},
            metadata={"requested_inputs": dict(inputs)},
        )
