from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class RunningHubWorkflowImagesNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.runninghub_workflow_images.v1",
            name="RunningHub Workflow Images",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "line_art_url": {"type": "string", "minLength": 1},
                    "image_urls": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "required": ["line_art_url", "image_urls"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "image_urls": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                    }
                },
                "required": ["image_urls"],
                "additionalProperties": False,
            },
            description="Assemble ordered image URLs for RunningHub workflow image inputs.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        line_art_url = inputs.get("line_art_url")
        if not isinstance(line_art_url, str) or not line_art_url.strip():
            raise ValidationError(
                code="runninghub_workflow_line_art_url_required",
                message="line_art_url cannot be empty",
            )

        raw_image_urls = inputs.get("image_urls")
        if not isinstance(raw_image_urls, list):
            raise ValidationError(
                code="runninghub_workflow_image_urls_required",
                message="image_urls must be an array",
            )

        image_urls = [item.strip() for item in raw_image_urls if isinstance(item, str) and item.strip()]
        if not image_urls:
            raise ValidationError(
                code="runninghub_workflow_image_urls_required",
                message="image_urls must include at least one URL",
            )

        return NodeResult(
            status="succeeded",
            output={"image_urls": [line_art_url.strip(), *image_urls]},
        )
