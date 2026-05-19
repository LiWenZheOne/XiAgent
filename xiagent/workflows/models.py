from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkflowTemplateRecord:
    template_id: str
    workflow_id: str
    version: str
    scope: str
    project_id: str | None
    name: str
    description: str | None
    contract: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkflowNodeSpec:
    id: str
    ref: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkflowEdgeSpec:
    from_node: str
    to_node: str
    when: dict[str, Any] | None = None
