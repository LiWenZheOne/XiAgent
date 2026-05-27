from __future__ import annotations

from xiagent.core.errors import ConflictError, NotFoundError
from xiagent.core.schemas import validate_json_schema
from xiagent.nodes.base import BaseNode
from xiagent.ui_controls.validation import validate_node_ui_defaults


class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, BaseNode] = {}

    def register(self, node: BaseNode) -> None:
        if not isinstance(node, BaseNode):
            raise TypeError("node must inherit BaseNode")
        descriptor = node.describe()
        if descriptor.ref in self._nodes:
            raise ConflictError(
                code="node_ref_exists",
                message="节点 ref 已存在",
                details={"ref": descriptor.ref},
            )
        validate_json_schema(descriptor.input_schema)
        validate_json_schema(descriptor.output_schema)
        if descriptor.config_schema is not None:
            validate_json_schema(descriptor.config_schema)
        validate_node_ui_defaults(
            node_ref=descriptor.ref,
            input_schema=descriptor.input_schema,
            output_schema=descriptor.output_schema,
            ui_defaults=descriptor.ui_defaults,
        )
        self._nodes[descriptor.ref] = node

    def get(self, ref: str) -> BaseNode:
        try:
            return self._nodes[ref]
        except KeyError as exc:
            raise NotFoundError(
                code="node_not_found",
                message="节点不存在",
                details={"ref": ref},
            ) from exc

    def list(self) -> list[BaseNode]:
        return list(self._nodes.values())
