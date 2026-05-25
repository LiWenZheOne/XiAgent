from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class CreateTextAssetNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.create_text_asset.v1",
            name="Create Text Asset",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["global", "project"],
                    },
                    "project_id": {"type": "string"},
                    "name": {"type": "string", "minLength": 1},
                    "text": {"type": "string", "minLength": 1},
                    "metadata": {"type": "object"},
                },
                "required": ["scope", "name", "text"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "minLength": 1},
                    "name": {"type": "string", "minLength": 1},
                    "asset_type": {"type": "string"},
                },
                "required": ["asset_id", "name", "asset_type"],
                "additionalProperties": False,
            },
            description="创建文本资产并写入资产库，支持 metadata.tags 四级标签。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        if ctx is None or ctx.asset_service is None:
            return NodeResult(
                status="failed",
                output={},
                error=ValidationError(
                    code="create_text_asset_no_context",
                    message="AssetService is not available in context",
                ),
            )

        scope = inputs.get("scope")
        if not isinstance(scope, str) or scope not in {"global", "project"}:
            raise ValidationError(
                code="create_text_asset_invalid_scope",
                message="scope must be global or project",
            )

        name = inputs.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValidationError(
                code="create_text_asset_name_required",
                message="name must be a non-empty string",
            )

        text = inputs.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValidationError(
                code="create_text_asset_text_required",
                message="text must be a non-empty string",
            )

        project_id = inputs.get("project_id")
        if project_id is not None and not isinstance(project_id, str):
            project_id = None

        metadata = inputs.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        record = await ctx.asset_service.create_text_asset(
            user_id=ctx.user_id,
            scope=scope,
            project_id=project_id if scope == "project" else None,
            name=name.strip(),
            text=text,
            metadata=metadata,
        )

        return NodeResult(
            status="succeeded",
            output={
                "asset_id": record.asset_id,
                "name": record.name,
                "asset_type": record.asset_type,
            },
        )
