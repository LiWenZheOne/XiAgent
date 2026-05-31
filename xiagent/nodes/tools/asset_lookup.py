from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class AssetLookupNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.asset_lookup.v1",
            name="Asset Lookup",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["global", "project", "combined"],
                    },
                    "keyword": {"type": "string"},
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "asset_type": {"type": "string"},
                    "mime_type": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    "match_mode": {
                        "type": "string",
                        "enum": ["exact", "contains"],
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["scope"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "total": {"type": "integer", "minimum": 0},
                    "assets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "asset_id": {"type": "string", "minLength": 1},
                                "name": {"type": "string", "minLength": 1},
                                "asset_type": {"type": "string"},
                                "mime_type": {"type": "string"},
                                "storage_uri": {"type": "string"},
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "metadata": {"type": "object"},
                            },
                            "required": ["asset_id", "name"],
                            "additionalProperties": True,
                        },
                    },
                },
                "required": ["total", "assets"],
                "additionalProperties": False,
            },
            description="查询已有资产库，返回匹配的资产列表，用于重复检查等场景。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        if ctx is None or ctx.asset_service is None:
            return NodeResult(status="succeeded", output={"total": 0, "assets": []})

        scope = inputs.get("scope")
        if not isinstance(scope, str) or scope not in {"global", "project", "combined"}:
            raise ValidationError(
                code="asset_lookup_invalid_scope",
                message="scope must be global, project or combined",
            )

        keyword = inputs.get("keyword")
        if not isinstance(keyword, str) or not keyword.strip():
            keyword = None

        names = inputs.get("names")
        if not isinstance(names, list) or not all(isinstance(n, str) and n.strip() for n in names):
            names = None
        elif names is not None:
            names = [n.strip() for n in names]

        asset_type = inputs.get("asset_type")
        if not isinstance(asset_type, str) or not asset_type.strip():
            asset_type = None

        mime_type = inputs.get("mime_type")
        if not isinstance(mime_type, str) or not mime_type.strip():
            mime_type = None

        limit = inputs.get("limit", 50)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            limit = 50

        match_mode = inputs.get("match_mode", "contains")
        if not isinstance(match_mode, str) or match_mode not in {"exact", "contains"}:
            match_mode = "contains"

        tags = inputs.get("tags")
        if not isinstance(tags, list) or not all(isinstance(t, str) and t.strip() for t in tags):
            tags = None
        elif tags is not None:
            tags = [t.strip() for t in tags]
            tags = [t for t in tags if t]

        project_id = ctx.project_id if scope in {"project", "combined"} else None

        if names is not None:
            keyword = None

        result = await ctx.asset_service.search_assets(
            user_id=ctx.user_id,
            scope=scope,
            project_id=project_id,
            keyword=keyword,
            asset_type=asset_type,
            mime_type=mime_type,
            tag_names=tags,
            limit=limit,
        )

        if match_mode == "exact" and keyword:
            result = type(result)(
                items=[item for item in result.items if item.name == keyword],
                total=sum(1 for item in result.items if item.name == keyword),
            )

        if names is not None:
            name_set = set(names)
            result = type(result)(
                items=[item for item in result.items if item.name in name_set],
                total=sum(1 for item in result.items if item.name in name_set),
            )

        assets: list[dict[str, Any]] = []
        for item in result.items:
            item_tags = await _asset_tag_names(ctx, item)
            asset_dict: dict[str, Any] = {
                "asset_id": item.asset_id,
                "name": item.name,
            }
            if item_tags:
                asset_dict["tags"] = item_tags
            if item.asset_type is not None:
                asset_dict["asset_type"] = item.asset_type
            if item.mime_type is not None:
                asset_dict["mime_type"] = item.mime_type
            if item.metadata is not None:
                asset_dict["metadata"] = item.metadata
            if item.text_content is not None:
                asset_dict["text_content"] = item.text_content
            if item.storage_uri is not None:
                asset_dict["storage_uri"] = item.storage_uri
            assets.append(asset_dict)

        return NodeResult(
            status="succeeded",
            output={"total": result.total, "assets": assets},
        )


async def _asset_tag_names(ctx: NodeContext, asset: Any) -> list[str]:
    records = await ctx.asset_service.list_asset_tags(
        user_id=ctx.user_id,
        asset_id=asset.asset_id,
    )
    return [
        tag.name.strip()
        for tag in records
        if isinstance(getattr(tag, "name", None), str) and tag.name.strip()
    ]
