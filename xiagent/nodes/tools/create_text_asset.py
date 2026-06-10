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
                        "enum": ["project"],
                    },
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
            description="创建文本资产并写入资产库；资产分类应使用资产库标签系统。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        if ctx is None or ctx.asset_service is None:
            raise ValidationError(
                code="create_text_asset_no_context",
                message="AssetService is not available in context",
            )

        scope = inputs.get("scope")
        if not isinstance(scope, str) or scope != "project":
            raise ValidationError(
                code="create_text_asset_invalid_scope",
                message="scope must be project",
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

        input_project_id = inputs.get("project_id")
        if input_project_id is not None and (
            not isinstance(input_project_id, str)
            or input_project_id != ctx.project_id
        ):
            raise ValidationError(
                code="create_text_asset_project_mismatch",
                message="project_id must match the node execution context",
            )

        metadata = inputs.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        record = await ctx.asset_service.create_text_asset(
            user_id=ctx.user_id,
            scope=scope,
            project_id=ctx.project_id,
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
