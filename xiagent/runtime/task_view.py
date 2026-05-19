from __future__ import annotations

from typing import Any

from xiagent.runtime.models import NodeExecutionRecord


def build_current_view(
    status: str,
    node_executions: list[NodeExecutionRecord],
    final_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_node_outputs: dict[str, str] = {}
    for execution in node_executions:
        if execution.status in {"succeeded", "waiting"}:
            active_node_outputs[execution.node_id] = execution.node_execution_id
    return {
        "status": status,
        "active_node_outputs": active_node_outputs,
        "final_output": final_output,
    }
