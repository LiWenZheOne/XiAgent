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

        filtered: dict[str, list[dict[str, Any]]] = {}
        for key in ("characters", "assets", "props"):
            value = approved_assets.get(key)
            items = value if isinstance(value, list) else []
            filtered_items: list[dict[str, Any]] = []
            for item in items:
                if not isinstance(item, Mapping) or _is_existing_asset(item):
                    continue
                filtered_items.append(
                    await _with_reference_context(ctx, dict(item))
                )
            filtered[key] = filtered_items

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


async def _with_reference_context(
    ctx: NodeContext | None,
    item: dict[str, Any],
) -> dict[str, Any]:
    item = _with_reference_image_ref(item)
    if not _optional_text(item.get("reference_variant_description")):
        description = _reference_variant_description(item)
        if not description:
            description = await _reference_variant_description_from_ref(ctx, item.get("reference_image_ref"))
        if description:
            item["reference_variant_description"] = description
    return item


def _with_reference_image_ref(item: dict[str, Any]) -> dict[str, Any]:
    if _valid_image_ref(item.get("reference_image_ref")):
        item["reference_image_ref"] = _clean_image_ref(item["reference_image_ref"])
        return item
    for key in ("matched_asset_ref", "default_variant_ref"):
        value = item.get(key)
        if _valid_image_ref(value):
            item["reference_image_ref"] = _clean_image_ref(value)
            return item
    for key in ("matched_variant_id", "asset_id", "matched_asset_id", "default_variant_asset_id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            item["reference_image_ref"] = {"kind": "asset", "asset_id": value.strip(), "role": "reference"}
            return item
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


def _clean_image_ref(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key in ("kind", "asset_id", "data", "role"):
        text = _optional_text(value.get(key))
        if text:
            result[key] = text
    return result


def _reference_variant_description(item: Mapping[str, Any]) -> str | None:
    for key in (
        "matched_asset_appearance_description",
        "reference_appearance_description",
        "default_variant_appearance_description",
        "reference_variant_description",
    ):
        value = _optional_text(item.get(key))
        if value:
            return value
    reference = item.get("reference_image_ref")
    if isinstance(reference, Mapping):
        value = _optional_text(reference.get("variant_description"))
        if value:
            return value
    return None


async def _reference_variant_description_from_ref(ctx: NodeContext | None, image_ref: Any) -> str | None:
    if ctx is None or ctx.asset_service is None or not isinstance(image_ref, Mapping):
        return None
    if image_ref.get("kind") != "asset":
        return None
    asset_id = _optional_text(image_ref.get("asset_id"))
    if not asset_id:
        return None
    try:
        asset = await ctx.asset_service.get_asset(
            user_id=ctx.user_id,
            asset_id=asset_id,
            project_id=ctx.project_id,
        )
    except Exception:
        return None
    return _asset_variant_description(asset)


def _asset_variant_description(asset: Any) -> str | None:
    metadata: Any
    if isinstance(asset, Mapping):
        metadata = asset.get("metadata")
    else:
        metadata = getattr(asset, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    for key in ("variant_description", "description", "appearance_description"):
        value = _optional_text(metadata.get(key))
        if value:
            return value
    return None


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
