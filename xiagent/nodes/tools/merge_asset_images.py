from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class MergeAssetImagesNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.merge_asset_images.v1",
            name="Merge Asset Images",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "manual_images": {"type": "array"},
                    "auto_images": {"type": "array"},
                },
                "additionalProperties": True,
            },
            output_schema={
                "type": "object",
                "required": ["asset_images"],
                "properties": {
                    "asset_images": {"type": "array"},
                },
                "additionalProperties": False,
            },
            description="Merge asset images from manual or auto path.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        manual = inputs.get("manual_images") or []
        auto = inputs.get("auto_images") or []
        merged = manual if manual else auto
        return NodeResult(status="succeeded", output={"asset_images": merged})
