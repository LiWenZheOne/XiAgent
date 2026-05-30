from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class FilterAssetsForGenerationNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.filter_assets_for_generation.v1",
            name="Filter Assets For Generation",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "approved_assets": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
                "required": ["approved_assets"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["approved_assets", "asset_count"],
                "properties": {
                    "approved_assets": {
                        "type": "object",
                        "required": ["characters", "assets", "props"],
                        "properties": {
                            "characters": {"type": "array", "items": {"type": "object"}},
                            "assets": {"type": "array", "items": {"type": "object"}},
                            "props": {"type": "array", "items": {"type": "object"}},
                        },
                        "additionalProperties": True,
                    },
                    "asset_count": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
            description="Filter out assets already matched to the asset library before prompt/image generation.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        approved_assets = inputs.get("approved_assets")
        if not isinstance(approved_assets, Mapping):
            raise ValidationError(
                code="filter_assets_approved_assets_required",
                message="approved_assets must be an object",
            )

        default_reference = await _default_template_ref(ctx)
        filtered: dict[str, list[dict[str, Any]]] = {}
        for key in ("characters", "assets", "props"):
            value = approved_assets.get(key)
            items = value if isinstance(value, list) else []
            filtered[key] = [
                _with_reference_image_ref(dict(item), default_reference)
                for item in items
                if isinstance(item, Mapping) and not _is_existing_asset(item)
            ]

        return NodeResult(
            status="succeeded",
            output={
                "approved_assets": filtered,
                "asset_count": sum(len(items) for items in filtered.values()),
            },
        )


def _is_existing_asset(item: Mapping[str, Any]) -> bool:
    if item.get("matched") is not True:
        return False
    for key in ("matched_asset_id", "matched_asset_name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _with_reference_image_ref(item: dict[str, Any], default_reference: dict[str, str] | None) -> dict[str, Any]:
    if _valid_image_ref(item.get("reference_image_ref")):
        return item
    for key in ("matched_asset_ref", "default_variant_ref"):
        value = item.get(key)
        if _valid_image_ref(value):
            item["reference_image_ref"] = value
            return item
    for key in ("matched_variant_id", "asset_id", "matched_asset_id", "default_variant_asset_id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            item["reference_image_ref"] = {"kind": "asset", "asset_id": value.strip(), "role": "reference"}
            return item
    if default_reference:
        item["reference_image_ref"] = dict(default_reference)
    return item


def _valid_image_ref(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    kind = value.get("kind")
    if kind == "asset":
        asset_id = value.get("asset_id")
        return isinstance(asset_id, str) and bool(asset_id.strip())
    if kind == "data_uri":
        data = value.get("data")
        return isinstance(data, str) and data.startswith("data:image/")
    return False


async def _default_template_ref(ctx: NodeContext | None) -> dict[str, str] | None:
    if ctx is None or ctx.asset_service is None:
        return None
    for keyword in ("塞雷2d模板", "塞雷无腿角色模板", "模板"):
        for scope, project_id in (("combined", ctx.project_id), ("global", None)):
            try:
                assets = await ctx.asset_service.search_assets(
                    user_id=ctx.user_id,
                    scope=scope,
                    project_id=project_id if scope == "combined" else None,
                    keyword=keyword,
                    mime_type="image/*",
                    limit=5,
                )
            except Exception:
                continue
            items = _asset_items(assets)
            for asset in items:
                asset_id = _asset_id(asset)
                name = _asset_name(asset)
                if asset_id and name == "塞雷2d模板":
                    return {"kind": "asset", "asset_id": asset_id, "role": "reference"}
            for asset in items:
                asset_id = _asset_id(asset)
                if asset_id:
                    return {"kind": "asset", "asset_id": asset_id, "role": "reference"}
    return None


def _asset_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    items = getattr(value, "items", None)
    return items if isinstance(items, list) else []


def _asset_id(asset: Any) -> str | None:
    if isinstance(asset, Mapping):
        value = asset.get("asset_id")
    else:
        value = getattr(asset, "asset_id", None)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _asset_name(asset: Any) -> str | None:
    if isinstance(asset, Mapping):
        value = asset.get("name")
    else:
        value = getattr(asset, "name", None)
    return value.strip() if isinstance(value, str) and value.strip() else None
