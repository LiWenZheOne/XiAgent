from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from xiagent.core.services import AssetService


@dataclass(frozen=True, slots=True)
class NodeDescriptor:
    ref: str
    name: str
    version: str
    kind: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    config_schema: dict[str, Any] | None = None
    description: str | None = None
    ui_defaults: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AssetRef:
    asset_id: str
    usage_type: str
    source: str


@dataclass(frozen=True, slots=True)
class NodeResult:
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    asset_refs: list[AssetRef] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class NodeContext:
    user_id: str
    project_id: str
    task_id: str
    node_id: str
    node_execution_id: str
    config: dict[str, Any]
    output_schema: dict[str, Any]
    asset_service: AssetService | None
    event_sink: Any
    logger: Any


class BaseNode(ABC):
    @abstractmethod
    def describe(self) -> NodeDescriptor:
        raise NotImplementedError

    @abstractmethod
    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        raise NotImplementedError
