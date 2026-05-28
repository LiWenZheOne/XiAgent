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
        output_schema = ctx.output_schema if ctx is not None else {}
        required = output_schema.get("required", [])
        if (
            isinstance(required, list)
            and required
            and all(isinstance(name, str) and name in inputs for name in required)
        ):
            return NodeResult(status="succeeded", output=dict(inputs))
        decision = inputs.get("decision")
        if isinstance(decision, str) and decision:
            return NodeResult(status="succeeded", output=dict(inputs))
        approved = inputs.get("approved")
        if isinstance(approved, bool):
            output = dict(inputs)
            output["decision"] = "approved" if approved else "rejected"
            return NodeResult(status="succeeded", output=output)
        return NodeResult(
            status="waiting",
            output={},
            metadata={"requested_inputs": dict(inputs)},
        )
