from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from xiagent.nodes.base import AssetRef


@dataclass(frozen=True, slots=True)
class TaskRecord:
    task_id: str
    workflow_template_id: str
    workflow_id: str
    workflow_version: str
    user_id: str
    project_id: str
    input_data: dict[str, Any]
    status: str
    current_view: dict[str, Any]
    created_at: str
    started_at: str | None
    finished_at: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class NodeExecutionRecord:
    node_execution_id: str
    task_id: str
    node_id: str
    node_ref: str
    attempt: int
    input_snapshot: dict[str, Any]
    output_snapshot: dict[str, Any]
    status: str
    error: dict[str, Any] | None
    metadata: dict[str, Any]
    started_at: str | None
    finished_at: str | None
    created_at: str
    updated_at: str
    asset_refs: list[AssetRef] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TaskEventRecord:
    event_id: str
    task_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str
