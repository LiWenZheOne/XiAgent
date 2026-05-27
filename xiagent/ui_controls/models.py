from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class UiControlBindingRequirement:
    name: str
    required: bool = True
    binding_kind: str = "schema_path"
    accepted_sources: tuple[str, ...] = (
        "workflow.input",
        "node.input",
        "node.output",
        "node.metadata",
        "nodes.output",
    )
    schema_constraints: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UiControlVariant:
    name: str
    label: str
    tags: tuple[str, ...] = ()
    modes: tuple[str, ...] = ("readonly",)
    required_bindings: tuple[UiControlBindingRequirement, ...] = ()
    submit_schema: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class UiControlDescriptor:
    control_id: str
    version: str
    name: str
    kind: str
    tags: tuple[str, ...]
    variants: tuple[UiControlVariant, ...]
    description: str | None = None
